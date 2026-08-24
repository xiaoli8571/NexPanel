"""REST API 路由（多节点版）"""
import re
import uuid as uuidlib

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import config, crypto, db, monitor, nodes as nodes_mod, security
from . import agent as agent_mod, deploy as deploy_mod
from .lxc import TEMPLATE_IMAGE_MAP, ops_for

router = APIRouter(prefix="/api")

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


# ────────────────────────── models ──────────────────────────
class LoginIn(BaseModel):
    username: str
    password: str


class NodeIn(BaseModel):
    name: str = Field(min_length=2, max_length=32)
    kind: str = Field("ssh", pattern="^(agent|ssh|demo)$")
    host: str = ""
    port: int = Field(22, ge=1, le=65535)
    username: str = "root"
    auth_type: str = Field("password", pattern="^(password|key)$")
    secret: str = ""


class ContainerIn(BaseModel):
    name: str = Field(min_length=2, max_length=32)
    node_id: int
    template: str
    cpu: int = Field(1, ge=1, le=16)
    mem: int = Field(512, ge=64, le=1048576, multiple_of=64)   # 支持 64M 粒度
    disk: int = Field(5, ge=1, le=2048)
    note: str = ""
    autostart: bool = False


class ActionIn(BaseModel):
    action: str = Field(pattern="^(start|stop|restart)$")


class SnapshotIn(BaseModel):
    name: str | None = None


class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=24)
    password: str = Field(min_length=6, max_length=64)
    role: str = Field("user", pattern="^(admin|user)$")


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=64)


# ────────────────────────── deps ──────────────────────────
def current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "未认证，请先登录")
    payload = security.decode_token(auth[7:])
    if not payload:
        raise HTTPException(401, "令牌无效或已过期")
    return payload


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


# ────────────────────────── meta / auth ──────────────────────────
@router.get("/meta")
def meta():
    n_total = db.one("SELECT COUNT(*) n FROM nodes")["n"]
    online = sum(1 for r in db.q("SELECT id FROM nodes")
                 if (monitor.get_cache(r["id"]) or {}).get("status") == "online")
    return {"brand": config.BRAND, "version": config.VERSION,
            "nodes_total": n_total, "nodes_online": online}


# ── 登录防爆破：同 IP 连续失败 5 次锁定 10 分钟 ──
_login_fail: dict[str, list] = {}
LOGIN_MAX_FAIL = 5
LOGIN_LOCK_SECONDS = 600


def _login_guard(ip: str):
    import time as _t
    rec = _login_fail.get(ip)
    if rec and rec[1] > _t.time():
        raise HTTPException(429, f"尝试次数过多，请 {int((rec[1] - _t.time()) / 60) + 1} 分钟后再试")


def _login_record(ip: str, ok: bool):
    import time as _t
    now = _t.time()
    if ok:
        _login_fail.pop(ip, None)
        return
    rec = _login_fail.get(ip)
    if not rec or (rec[1] and rec[1] < now):
        rec = [0, 0]
    rec[0] += 1
    if rec[0] >= LOGIN_MAX_FAIL:
        rec[1] = now + LOGIN_LOCK_SECONDS
        rec[0] = 0
    _login_fail[ip] = rec


@router.post("/login")
def login(body: LoginIn, request: Request):
    ip = request.client.host if request.client else ""
    _login_guard(ip)
    u = db.one("SELECT * FROM users WHERE username=?", (body.username,))
    if not u or not security.verify_password(body.password, u["pw_hash"]):
        _login_record(ip, False)
        raise HTTPException(401, "用户名或密码错误")
    _login_record(ip, True)
    token = security.make_token({"uid": u["id"], "sub": u["username"], "role": u["role"]})
    db.audit(u["username"], "登录", "system", "", ip)
    return {"token": token, "user": {"username": u["username"], "role": u["role"]}}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"username": user["sub"], "role": user["role"]}


@router.post("/me/password")
def change_password(body: PasswordIn, user: dict = Depends(current_user)):
    row = db.one("SELECT * FROM users WHERE id=?", (user["uid"],))
    if not row or not security.verify_password(body.old_password, row["pw_hash"]):
        raise HTTPException(400, "原密码不正确")
    db.ex("UPDATE users SET pw_hash=? WHERE id=?",
          (security.hash_password(body.new_password), user["uid"]))
    db.audit(user["sub"], "修改密码", user["sub"])
    return {"ok": True}


# ────────────────────────── nodes ──────────────────────────
def _node_out(row) -> dict:
    s = monitor.summary_of(row)
    out = {**{k: row[k] for k in ("id", "name", "kind", "host", "port",
                                  "username", "auth_type", "created_at",
                                  "public_ip")},
           **s}
    if row["kind"] == "agent":
        out["agent_token"] = row["agent_token"]
        base = config.PUBLIC_BASE or ""
        out["install_cmd"] = (
            f"curl -fsSL {base}/api/agent/install.sh | bash -s -- "
            f"--api {base} --token {row['agent_token']}") if base else             f"(配置 PUBLIC_BASE 后生成) token={row['agent_token']}"
    return out


def _get_node(nid: int):
    row = db.one("SELECT * FROM nodes WHERE id=?", (nid,))
    if not row:
        raise HTTPException(404, "节点不存在")
    return dict(row)


@router.get("/nodes")
def list_nodes(user: dict = Depends(current_user)):
    return [_node_out(r) for r in db.q("SELECT * FROM nodes ORDER BY id")]


@router.post("/nodes", status_code=201)
def create_node(body: NodeIn, request: Request, admin: dict = Depends(require_admin)):
    if body.kind == "ssh":
        if not body.host or not body.username:
            raise HTTPException(400, "SSH 节点必须填写主机地址与用户名")
        if not body.secret.strip():
            raise HTTPException(400, "请填写密码或私钥")
    if db.one("SELECT 1 FROM nodes WHERE name=?", (body.name,)):
        raise HTTPException(400, f"节点名 {body.name} 已存在")

    secret_enc = crypto.enc(body.secret.strip()) if (body.kind == "ssh" and body.secret.strip()) else ""
    agent_token = agent_mod.new_token() if body.kind == "agent" else ""
    db.ex("""INSERT INTO nodes(name,kind,host,port,username,auth_type,secret,agent_token,status,created_at)
             VALUES(?,?,?,?,?,?,?,?,'unknown',?)""",
          body.name.strip(), body.kind,
          body.host.strip() if body.kind == "ssh" else "",
          body.port, body.username.strip(), body.auth_type,
          secret_enc, agent_token, db.now())
    row = dict(db.one("SELECT * FROM nodes WHERE name=?", (body.name.strip(),)))
    monitor.start_node(row)
    db.audit(admin["sub"], "添加节点", body.name.strip(),
             f"{body.kind} {body.host}:{body.port}".strip(), request.client.host)
    return _node_out(row)


@router.post("/nodes/test")
def test_node_body(body: NodeIn, admin: dict = Depends(require_admin)):
    """未保存前的连接测试"""
    if body.kind != "ssh":
        raise HTTPException(400, "演示节点无需测试")
    temp = {"host": body.host.strip(), "port": body.port,
            "username": body.username.strip(),
            "auth_type": body.auth_type, "secret": crypto.enc(body.secret)}
    try:
        return nodes_mod.test_node(temp)
    except Exception as e:
        raise HTTPException(400, f"连接失败: {e}")


@router.post("/nodes/{nid}/probe")
def probe_node(nid: int, admin: dict = Depends(require_admin)):
    """对已保存节点做连接探测并更新状态"""
    node = _get_node(nid)
    if node["kind"] != "ssh":
        return {"ok": True, "os": "Demo Runtime", "lxc_installed": True}
    try:
        info = nodes_mod.test_node(node)
        status = "online" if info["lxc_installed"] else "nolxc"
        db.ex("UPDATE nodes SET status=?, lxc_ok=?, os_info=? WHERE id=?",
              (status, int(info["lxc_installed"]), info["os"], nid))
        return info
    except Exception as e:
        db.ex("UPDATE nodes SET status='offline' WHERE id=?", (nid,))
        raise HTTPException(400, f"连接失败: {e}")


@router.post("/nodes/{nid}/install")
def install_node_lxc(nid: int, request: Request, admin: dict = Depends(require_admin)):
    node = _get_node(nid)
    if node["kind"] != "ssh":
        raise HTTPException(400, "演示节点无需安装")
    try:
        output = nodes_mod.install_lxc(node)
    except Exception as e:
        raise HTTPException(500, str(e)[-600:])
    db.ex("UPDATE nodes SET status='online', lxc_ok=1 WHERE id=?", (nid,))
    db.audit(admin["sub"], "安装LXC", node["name"], "", request.client.host)
    return {"ok": True, "output": output[-800:]}


@router.delete("/nodes/{nid}")
def delete_node(nid: int, request: Request, force: int = 0,
                admin: dict = Depends(require_admin)):
    node = _get_node(nid)
    children = db.one("SELECT COUNT(*) n FROM containers WHERE node_id=?", (nid,))["n"]
    if children and not force:
        raise HTTPException(400, f"该节点下还有 {children} 台实例，请先删除或使用强制删除")
    ops = ops_for(node)
    for c in db.q("SELECT * FROM containers WHERE node_id=?", (nid,)):
        try:
            ops.delete(dict(c))
        except Exception:
            pass
        db.ex("DELETE FROM snapshots WHERE container_id=?", (c["id"],))
    db.ex("DELETE FROM containers WHERE node_id=?", (nid,))
    monitor.stop_node(nid)
    db.ex("DELETE FROM nodes WHERE id=?", (nid,))
    db.audit(admin["sub"], "删除节点", node["name"], "", request.client.host)
    return {"ok": True}


# ────────────────────────── agent REST ──────────────────────────
from fastapi import Request as _Req
from fastapi.responses import PlainTextResponse, JSONResponse


@router.get("/agent/agent.py")
def agent_py(token: str = ""):
    return PlainTextResponse(agent_mod.AGENT_PY, media_type="text/x-python")


@router.get("/agent/install.sh")
def install_sh(request: _Req, token: str = "", api: str = ""):
    base = api or config.PUBLIC_BASE or str(request.base.url).rstrip("/")
    script = agent_mod.INSTALL_SH.replace("__API__", base).replace("__TOKEN__", token)
    return PlainTextResponse(script, media_type="text/x-shellscript")


@router.post("/agent/poll")
async def agent_poll(request: _Req):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ag_"):
        raise HTTPException(401, "bad agent")
    row = db.one("SELECT id FROM nodes WHERE agent_token=?", (auth[7:],))
    if not row:
        raise HTTPException(401, "unknown agent")
    nid = row["id"]
    try:
        report = await request.json()
    except Exception:
        report = {}
    agent_mod.touch(nid)
    monitor.agent_report(nid, report)
    cmds = agent_mod.pop_pending(nid)
    return {"commands": cmds}


@router.post("/agent/result")
async def agent_result(request: _Req):
    payload = await request.json()
    agent_mod.push_result(payload["id"], int(payload.get("rc", 0)),
                          base64_decode(payload.get("out", "")))
    return {"ok": True}


def base64_decode(s: str) -> str:
    import base64
    try:
        return base64.b64decode(s.encode()).decode(errors="replace")
    except Exception:
        return ""


@router.post("/nodes/{nid}/rotate-token")
def rotate_token(nid: int, admin: dict = Depends(require_admin)):
    node = _get_node(nid)
    if node["kind"] != "agent":
        raise HTTPException(400, "仅 Agent 节点支持")
    tok = agent_mod.new_token()
    db.ex("UPDATE nodes SET agent_token=? WHERE id=?", (tok, nid))
    return {"ok": True, "agent_token": tok}


# ────────────────────────── 一键部署 ──────────────────────────
class DeployIn(BaseModel):
    container_id: int
    app_type: str
    start_port: int = Field(8881, ge=1024, le=65528)
    sni: str = ""


@router.get("/apps/catalog")
def apps_catalog(user: dict = Depends(current_user)):
    return [{"type": k, **{kk: vv for kk, vv in v.items() if kk != "single"}}
            for k, v in deploy_mod.CATALOG.items()]


@router.get("/apps")
def list_apps(user: dict = Depends(current_user)):
    return [dict(r) for r in db.q("""
        SELECT a.id, a.container_id, a.name, a.app_type, a.links, a.status,
               a.created_at, c.name AS container
        FROM apps a LEFT JOIN containers c ON c.id=a.container_id
        ORDER BY a.id DESC""")]


@router.post("/deploy")
async def deploy(body: DeployIn, request: Request, user: dict = Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "部署需要管理员权限")
    try:
        job_id = await deploy_mod.start_deploy(
            body.container_id, body.app_type,
            body.start_port, body.sni.strip() or "",
            user, request.client.host)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"job_id": job_id}


@router.get("/deploy/{job_id}")
def deploy_status(job_id: str, user: dict = Depends(current_user)):
    snap = deploy_mod.job_snapshot(job_id)
    if not snap:
        raise HTTPException(404, "任务不存在")
    return snap


@router.delete("/apps/{app_id}")
async def del_app(app_id: int, request: Request, user: dict = Depends(require_admin)):
    try:
        await deploy_mod.remove_app(app_id, user, request.client.host)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


# ────────────────────────── overview ──────────────────────────
@router.get("/overview")
def overview(user: dict = Depends(current_user)):
    nodes_rows = [dict(r) for r in db.q("SELECT * FROM nodes ORDER BY id")]
    summaries = [monitor.summary_of(n) for n in nodes_rows]

    agg_cpu = [s["live"]["cpu_pct"] for s in summaries if s["status"] == "online"]
    mem_t = sum(s["live"]["mem_total_mb"] for s in summaries)
    mem_u = sum(s["live"]["mem_used_mb"] for s in summaries)
    disk_t = sum(s["live"]["disk_total_gb"] for s in summaries)
    disk_u = sum(s["live"]["disk_used_gb"] for s in summaries)

    counts = {"total": 0, "running": 0, "stopped": 0}
    top = []
    rows = [dict(r) for r in db.q("SELECT * FROM containers")]
    for r in rows:
        counts["total"] += 1
        counts["running" if r["status"] == "running" else "stopped"] += 1
        live = monitor.container_live(r)
        nmap = {n["id"]: n["name"] for n in nodes_rows}
        top.append({"name": r["name"], "node": nmap.get(r["node_id"], "-"),
                    "status": r["status"], "cpu_pct": live["cpu_pct"],
                    "mem_used_mb": live["mem_used_mb"], "mem_mb": r["mem"]})
    return {
        "agg": {"cpu_pct": round(sum(agg_cpu) / len(agg_cpu), 1) if agg_cpu else 0,
                "mem_total_mb": mem_t, "mem_used_mb": mem_u,
                "disk_total_gb": round(disk_t, 1), "disk_used_gb": round(disk_u, 1),
                "nodes_total": len(nodes_rows),
                "nodes_online": sum(1 for s in summaries if s["status"] == "online")},
        "counts": counts,
        "nodes_summary": summaries,
        "top": sorted(top, key=lambda x: -x["cpu_pct"])[:5],
        "sum_mem_mb": int(mem_u),
    }


# ────────────────────────── containers ──────────────────────────
def _row_out(r: dict) -> dict:
    snaps = db.one("SELECT COUNT(*) n FROM snapshots WHERE container_id=?", (r["id"],))["n"]
    node_row = db.one("SELECT name,kind FROM nodes WHERE id=?", (r["node_id"],)) if r["node_id"] else None
    live = monitor.container_live(r)
    return {**{k: r[k] for k in ("id", "uuid", "name", "node_id", "template", "status",
                                 "cpu", "mem", "disk", "ip", "note", "created_at")},
            "distro": r["template"].split("-")[0],
            "node_name": node_row["name"] if node_row else "(已删除)",
            "node_kind": node_row["kind"] if node_row else "",
            "snapshots": snaps, "live": live}


@router.get("/containers")
def list_containers(q: str = "", status: str = "all", node: int | None = None,
                    user: dict = Depends(current_user)):
    sql, args = "SELECT * FROM containers WHERE 1=1", []
    if status in ("running", "stopped"):
        sql += " AND status=?"; args.append(status)
    if node:
        sql += " AND node_id=?"; args.append(node)
    rows = [dict(r) for r in db.q(sql, *args)]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["name"].lower() or ql in (r["ip"] or "")
                or ql in r["template"].lower()]
    return [_row_out(r) for r in rows]


def _do(node: dict, op: str, c: dict):
    """在指定节点上执行容器操作"""
    ops = ops_for(node)
    getattr(ops, op)(c) if node["kind"] == "demo" else getattr(ops, op)(node, c)


@router.post("/containers", status_code=201)
def create_container(body: ContainerIn, request: Request, user: dict = Depends(current_user)):
    name = body.name.strip().lower()
    if not NAME_RE.match(name):
        raise HTTPException(400, "名称需以字母开头，仅含小写字母/数字/连字符")
    if db.one("SELECT id FROM containers WHERE name=?", (name,)):
        raise HTTPException(400, f"实例名 {name} 已存在")
    if not db.one("SELECT 1 FROM templates WHERE key=?", (body.template,)):
        raise HTTPException(400, f"未知模板 {body.template}")
    node = _get_node(body.node_id)

    cid = uuidlib.uuid4().hex[:16]
    ip = ""
    if node["kind"] == "demo":
        used = {r["ip"] for r in db.q("SELECT ip FROM containers")}
        ip = next((f"10.0.0.{i}" for i in range(2, 251)
                   if f"10.0.0.{i}" not in used), "")
    db.ex("""INSERT INTO containers(uuid,name,node_id,template,status,cpu,mem,disk,ip,note,created_at)
             VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
          cid, name, node["id"], body.template, "stopped",
          body.cpu, body.mem, body.disk, ip, body.note, db.now())
    c = dict(db.one("SELECT * FROM containers WHERE uuid=?", (cid,)))
    detail = f"{body.template} / {body.cpu}C·{body.mem}M·{body.disk}G @{node['name']}"
    db.audit(user["sub"], "创建实例", name, detail, request.client.host)
    try:
        _do(node, "create", c)
        if body.autostart:
            _do(node, "start", c)
            db.ex("UPDATE containers SET status='running' WHERE uuid=?", (cid,))
            db.audit(user["sub"], "启动", name, "创建后自启", request.client.host)
    except Exception as e:
        db.ex("DELETE FROM containers WHERE uuid=?", (cid,))
        msg = str(e)
        tail = msg[-300:]
        raise HTTPException(500, f"节点上创建失败: {tail}")
    return _row_out(dict(db.one("SELECT * FROM containers WHERE uuid=?", (cid,))))


@router.post("/containers/{cid}/action")
def container_action(cid: int, body: ActionIn, request: Request,
                     user: dict = Depends(current_user)):
    row = db.one("SELECT * FROM containers WHERE id=?", (cid,))
    if not row:
        raise HTTPException(404, "实例不存在")
    c = dict(row)
    node = _get_node(c["node_id"]) if c["node_id"] else None
    if not node:
        raise HTTPException(400, "实例未关联有效节点")
    try:
        _do(node, body.action, c)
    except Exception as e:
        raise HTTPException(500, f"操作失败: {str(e)[-300:]}")
    new_status = {"start": "running", "stop": "stopped", "restart": "running"}[body.action]
    db.ex("UPDATE containers SET status=? WHERE id=?", (new_status, cid))
    db.audit(user["sub"], {"start": "启动", "stop": "停止", "restart": "重启"}[body.action],
             c["name"], f"@{node['name']}", request.client.host)
    return {"ok": True, "status": new_status}


@router.delete("/containers/{cid}")
def delete_container(cid: int, request: Request, user: dict = Depends(require_admin)):
    row = db.one("SELECT * FROM containers WHERE id=?", (cid,))
    if not row:
        raise HTTPException(404, "实例不存在")
    c = dict(row)
    node = _get_node(c["node_id"]) if c["node_id"] else None
    if node:
        try:
            _do(node, "delete", c)
        except Exception:
            pass
    db.ex("DELETE FROM snapshots WHERE container_id=?", (cid,))
    db.ex("DELETE FROM containers WHERE id=?", (cid,))
    db.audit(user["sub"], "删除实例", c["name"], "", request.client.host)
    return {"ok": True}


# ────────────────────────── templates ──────────────────────────
@router.get("/templates")
def templates(user: dict = Depends(current_user)):
    out = []
    for r in db.q("SELECT * FROM templates ORDER BY size_mb"):
        d = dict(r)
        d["supported"] = d["key"] in TEMPLATE_IMAGE_MAP
        out.append(d)
    return out


# ────────────────────────── snapshots ──────────────────────────
@router.get("/snapshots")
def list_snapshots(user: dict = Depends(current_user)):
    return [dict(r) for r in db.q("""
        SELECT s.id, s.container_id, s.name, s.size_mb, s.created_at, c.name AS container
        FROM snapshots s LEFT JOIN containers c ON c.id = s.container_id
        ORDER BY s.id DESC""")]


@router.post("/containers/{cid}/snapshots", status_code=201)
def create_snapshot(cid: int, body: SnapshotIn, request: Request,
                    user: dict = Depends(current_user)):
    row = db.one("SELECT * FROM containers WHERE id=?", (cid,))
    if not row:
        raise HTTPException(404, "实例不存在")
    name = (body.name or f"snap-{db.now().replace(' ', '-')}").strip()
    size = round(row["disk"] * 1024 * .21 + 120, 1)
    db.ex("INSERT INTO snapshots(container_id,name,size_mb,created_at) VALUES(?,?,?,?)",
          cid, name, size, db.now())
    db.audit(user["sub"], "创建快照", row["name"], name, request.client.host)
    return {"ok": True, "name": name, "size_mb": size}


@router.post("/snapshots/{sid}/restore")
def restore_snapshot(sid: int, request: Request, user: dict = Depends(current_user)):
    s = db.one("""SELECT s.*, c.name AS cname FROM snapshots s
                  JOIN containers c ON c.id=s.container_id WHERE s.id=?""", (sid,))
    if not s:
        raise HTTPException(404, "快照不存在")
    db.audit(user["sub"], "恢复快照", s["cname"], s["name"], request.client.host)
    return {"ok": True, "message": f"已回滚到快照 {s['name']}"}


@router.delete("/snapshots/{sid}")
def delete_snapshot(sid: int, request: Request, user: dict = Depends(current_user)):
    s = db.one("SELECT * FROM snapshots WHERE id=?", (sid,))
    if not s:
        raise HTTPException(404, "快照不存在")
    db.ex("DELETE FROM snapshots WHERE id=?", (sid,))
    db.audit(user["sub"], "删除快照", str(s["container_id"]), s["name"], request.client.host)
    return {"ok": True}


# ────────────────────────── network(IP 分配总览) ──────────────────────────
@router.get("/network")
def network(user: dict = Depends(current_user)):
    rows = db.q("""SELECT c.ip, c.name, c.status, n.name AS node
                   FROM containers c LEFT JOIN nodes n ON n.id=c.node_id ORDER BY n.id, c.ip""")
    allocations = [{"ip": r["ip"], "container": r["name"],
                    "status": r["status"], "node": r["node"] or "(已删除)"} for r in rows]
    nodes_rows = [dict(r) for r in db.q("SELECT * FROM nodes")]
    bridges = []
    for n in nodes_rows:
        cnt = db.one("SELECT COUNT(*) n FROM containers WHERE node_id=?", (n["id"],))["n"]
        entry = monitor.get_cache(n["id"]) or {}
        bridges.append({"name": n["name"], "kind": n["kind"], "state": entry.get("status", "unknown"),
                        "used": cnt})
    return {"allocations": allocations, "bridges": bridges}


# ────────────────────────── users ──────────────────────────
@router.get("/users")
def list_users(user: dict = Depends(current_user)):
    return [dict(r) for r in db.q("SELECT id,username,role,created_at FROM users ORDER BY id")]


@router.post("/users", status_code=201)
def create_user(body: UserIn, request: Request, admin: dict = Depends(require_admin)):
    if db.one("SELECT 1 FROM users WHERE username=?", (body.username,)):
        raise HTTPException(400, "用户已存在")
    db.ex("INSERT INTO users(username,pw_hash,role,created_at) VALUES(?,?,?,?)",
          body.username, security.hash_password(body.password), body.role, db.now())
    db.audit(admin["sub"], "创建用户", body.username, f"角色 {body.role}", request.client.host)
    return {"ok": True}


@router.delete("/users/{uid}")
def delete_user(uid: int, request: Request, admin: dict = Depends(require_admin)):
    row = db.one("SELECT * FROM users WHERE id=?", (uid,))
    if not row:
        raise HTTPException(404, "用户不存在")
    if row["username"] == "admin":
        raise HTTPException(400, "不能删除内置管理员")
    if row["id"] == admin["uid"]:
        raise HTTPException(400, "不能删除当前登录账号")
    db.ex("DELETE FROM users WHERE id=?", (uid,))
    db.audit(admin["sub"], "删除用户", row["username"], "", request.client.host)
    return {"ok": True}


# ────────────────────────── audit ──────────────────────────
@router.get("/audit")
def audit_list(limit: int = 100, user: dict = Depends(current_user)):
    limit = min(max(limit, 1), 500)
    return [dict(r) for r in db.q("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]


# ────────────────────────── admin ops ──────────────────────────
@router.post("/admin/reset-instances")
@router.post("/admin/reset-demo")
def reset_instances(request: Request, admin: dict = Depends(require_admin)):
    from .lxc import DemoRuntime
    db.wipe_instances()
    for rt in monitor._demo_runtimes.values():
        rt.reset()
    db.audit(admin["sub"], "清空实例数据", "system", "", request.client.host)
    return {"ok": True}
