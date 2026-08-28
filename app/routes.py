"""REST API 路由（多节点版）"""
import json
import os
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
    kind: str = Field("ssh", pattern="^(agent|ssh|demo|probe)$")
    role: str = Field("manage", pattern="^(manage|probe)$")
    host: str = ""
    port: int = Field(22, ge=1, le=65535)
    username: str = "root"
    auth_type: str = Field("password", pattern="^(password|key)$")
    secret: str = ""
    install_lxc: bool = False       # True=作为母机，接入后自动安装 LXC；False=仅部署节点


class ContainerIn(BaseModel):
    name: str = Field(min_length=2, max_length=32)
    node_id: int
    template: str
    cpu: int = Field(1, ge=1, le=16)
    mem: int = Field(512, ge=64, le=1048576, multiple_of=64)   # 支持 64M 粒度
    swap: int = Field(0, ge=0, le=1048576)                     # swap 内存 MB，0=不额外设置
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
    online = sum(1 for r in db.q("SELECT * FROM nodes")
                 if monitor.summary_of(r)["status"] in ("online", "nolxc"))
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
                                  "public_ip", "role", "install_lxc")},
           **s}
    if row["kind"] == "agent":
        out["agent_token"] = row["agent_token"]
    return out


def _get_node(nid: int):
    row = db.one("SELECT * FROM nodes WHERE id=?", (nid,))
    if not row:
        raise HTTPException(404, "节点不存在")
    return dict(row)


def _uninstall_cmd(base: str) -> str:
    return f"curl -fsSL {base}/api/agent/uninstall.sh | bash"


@router.get("/nodes")
def list_nodes(request: Request, user: dict = Depends(current_user)):
    base = _panel_base(request)
    out = []
    for r in db.q("SELECT * FROM nodes ORDER BY sort_order, id"):
        d = _node_out(r)
        if r["kind"] == "agent":
            d["install_cmd"] = _install_cmd(base, r["agent_token"])
            d["uninstall_cmd"] = _uninstall_cmd(base)
        out.append(d)
    return out


def _panel_base(request: Request) -> str:
    """面板对外地址：优先环境变量，其次请求 Host"""
    if config.PUBLIC_BASE:
        return config.PUBLIC_BASE
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto",
             "https" if request.url.scheme == "https" else "http")
    return f"{scheme}://{host}" if host else ""


def _install_cmd(base: str, token: str) -> str:
    # 用 sh 而非 bash：部分 Alpine/minimal 系统可能没装 bash
    return (f"curl -fsSL {base}/api/agent/install.sh | sh -s -- "
            f"--api {base} --token {token}")


@router.post("/nodes", status_code=201)
def create_node(body: NodeIn, request: Request, admin: dict = Depends(require_admin)):
    kind = body.kind
    role = body.role
    if kind == "probe":                     # 探针本质 = 只读 Agent
        kind, role = "agent", "probe"
    if body.kind == "ssh":
        if not body.host or not body.username:
            raise HTTPException(400, "SSH 节点必须填写主机地址与用户名")
        if not body.secret.strip():
            raise HTTPException(400, "请填写密码或私钥")
    if db.one("SELECT 1 FROM nodes WHERE name=?", (body.name,)):
        raise HTTPException(400, f"节点名 {body.name} 已存在")

    secret_enc = crypto.enc(body.secret.strip()) if (body.kind == "ssh" and body.secret.strip()) else ""
    agent_token = agent_mod.new_token() if kind == "agent" else ""
    db.ex("""INSERT INTO nodes(name,kind,role,host,port,username,auth_type,secret,agent_token,status,install_lxc,created_at)
             VALUES(?,?,?,?,?,?,?,?,?,'unknown',?,?)""",
          body.name.strip(), kind, role,
          body.host.strip() if body.kind == "ssh" else "",
          body.port, body.username.strip(), body.auth_type,
          secret_enc, agent_token,
          int(body.install_lxc) if kind in ("agent", "ssh") else 0,
          db.now())
    row = dict(db.one("SELECT * FROM nodes WHERE name=?", (body.name.strip(),)))
    if row["kind"] == "agent":
        monitor.touch_from_db(row)
        out = _node_out(row)
        base = _panel_base(request)
        out["install_cmd"] = _install_cmd(base, row["agent_token"])
        out["uninstall_cmd"] = _uninstall_cmd(base)
        db.audit(admin["sub"], "添加节点", body.name.strip(),
                 f"{body.kind} {body.role}".strip(), request.client.host)
        return out
    # SSH 节点创建后立即启动后台监控（否则要等面板重启才有负载数据）
    if row["kind"] == "ssh":
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
        # 对已存在的 SSH 节点也启动后台监控（修复旧节点不采集负载）
        monitor.start_node(node)
        return info
    except Exception as e:
        db.ex("UPDATE nodes SET status='offline' WHERE id=?", (nid,))
        raise HTTPException(400, f"连接失败: {e}")


@router.post("/nodes/{nid}/install")
async def install_node_lxc(nid: int, request: Request, admin: dict = Depends(require_admin)):
    """一键给母鸡安装 LXC —— Agent 节点走命令通道，SSH 节点走远程执行"""
    import asyncio as _aio
    node = _get_node(nid)
    if node["kind"] == "demo":
        raise HTTPException(400, "演示节点无需安装")
    if node["kind"] == "agent" and not agent_mod.is_online(nid):
        raise HTTPException(400, "Agent 离线，无法下发安装指令")

    INSTALL_LXC = (
        "export DEBIAN_FRONTEND=noninteractive\n"
        "if command -v apt-get >/dev/null 2>&1; then apt-get update -qq; apt-get install -y -qq lxc; "
        "elif command -v dnf >/dev/null 2>&1; then dnf install -y lxc lxc-templates; "
        "elif command -v yum >/dev/null 2>&1; then yum install -y lxc lxc-templates; "
        "elif command -v apk >/dev/null 2>&1; then apk add --no-cache lxc lxc-templates; "
        "else echo unsupported; exit 9; fi\n"
        "command -v lxc-start && lxc-start --version")

    try:
        if node["kind"] == "agent":
            cid = agent_mod.queue_exec(nid, INSTALL_LXC, timeout=900)
            res = await _aio.to_thread(agent_mod.wait_result, cid, 950)
            if res is None:
                raise RuntimeError("安装超时（可稍后重试，apt 可能仍在后台进行）")
            rc, out = res["rc"], res["out"]
        else:
            rc, out = await _aio.to_thread(nodes_mod.run_cmd, node, INSTALL_LXC, 900, True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e)[-500:])

    tail = "\n".join(out.splitlines()[-20:])
    ok = ("MISSING" not in out) and (rc == 0)
    db.ex("UPDATE nodes SET status=?, lxc_ok=? WHERE id=?",
          ("online" if ok else "nolxc", int(ok), nid))
    db.audit(admin["sub"], "安装LXC", node["name"],
             "成功" if ok else tail[-120:], request.client.host)
    if not ok:
        raise HTTPException(500, f"安装失败:\n{tail[-400:]}")
    return {"ok": True, "output": tail[-800:]}


@router.delete("/nodes/{nid}")
def delete_node(nid: int, request: Request, force: int = 0,
                admin: dict = Depends(require_admin)):
    node = _get_node(nid)
    children = db.one("SELECT COUNT(*) n FROM containers WHERE node_id=?", (nid,))["n"]
    if children and not force:
        raise HTTPException(400, f"该节点下还有 {children} 台实例，请先删除或使用强制删除")
    ops = ops_for(node)
    ct_ids = []
    for c in db.q("SELECT * FROM containers WHERE node_id=?", (nid,)):
        ct_ids.append(c["id"])
        try:
            ops.delete(dict(c))
        except Exception:
            pass
        db.ex("DELETE FROM snapshots WHERE container_id=?", (c["id"],))
    db.ex("DELETE FROM containers WHERE node_id=?", (nid,))

    # 清理该节点下发的应用（node_id 直装 + 容器内部署），节点已删除不再做远端清理
    app_ids = set()
    for r in db.q("SELECT id FROM apps WHERE node_id=?", (nid,)):
        app_ids.add(r["id"])
    if ct_ids:
        placeholders = ",".join("?" * len(ct_ids))
        for r in db.q(f"SELECT id FROM apps WHERE container_id IN ({placeholders})", *ct_ids):
            app_ids.add(r["id"])
    if app_ids:
        ids = list(app_ids)
        ph = ",".join("?" * len(ids))
        db.ex(f"DELETE FROM subscription_limits WHERE app_id IN ({ph})", *ids)
        db.ex(f"DELETE FROM apps WHERE id IN ({ph})", *ids)

    db.ex("DELETE FROM nodes WHERE id=?", (nid,))
    # 清理监控/审计为“尽力而为”，即使 VPS 已删除也不影响节点删除成功
    try:
        monitor.stop_node(nid)
    except Exception:
        pass
    try:
        db.audit(admin["sub"], "删除节点", node["name"],
                 f"同时清理 {len(app_ids)} 个应用" if app_ids else "", request.client.host)
    except Exception:
        pass
    return {"ok": True}


class ReorderIn(BaseModel):
    ids: list[int]


class SwapIn(BaseModel):
    size_gb: int = Field(1, ge=1, le=64)


@router.post("/nodes/reorder")
def reorder_nodes(body: ReorderIn, request: Request,
                  admin: dict = Depends(require_admin)):
    """按传入顺序更新节点 sort_order"""
    for i, nid in enumerate(body.ids):
        db.ex("UPDATE nodes SET sort_order=? WHERE id=?", (i, nid))
    db.audit(admin["sub"], "调整节点排序", "system", "", request.client.host)
    return {"ok": True}


class NodeRenameIn(BaseModel):
    name: str = Field(min_length=2, max_length=32)


@router.put("/nodes/{nid}")
def rename_node(nid: int, body: NodeRenameIn, request: Request,
                admin: dict = Depends(require_admin)):
    """修改已添加节点的名称"""
    node = _get_node(nid)
    new_name = body.name.strip()
    if db.one("SELECT id FROM nodes WHERE name=? AND id!=?", (new_name, nid)):
        raise HTTPException(400, "节点名已存在")
    db.ex("UPDATE nodes SET name=? WHERE id=?", (new_name, nid))
    db.audit(admin["sub"], "重命名节点", node["name"], new_name, request.client.host)
    return {"ok": True, "name": new_name}


@router.post("/nodes/{nid}/import-lxc")
async def import_host_lxc(nid: int, request: Request,
                          admin: dict = Depends(require_admin)):
    """把宿主机上已有的 LXC 容器导入面板（例如面板自身所在容器）"""
    from . import deploy as deploy_mod
    node = _get_node(nid)
    if node["kind"] not in ("agent", "ssh"):
        raise HTTPException(400, "仅支持 Agent/SSH 节点导入")
    script = r'''
for n in $(lxc-ls -1 2>/dev/null); do
  st=$(lxc-info -s -n "$n" 2>/dev/null | awk '{print $2}')
  ip=$(lxc-info -iH -n "$n" 2>/dev/null | head -1)
  echo "CT|$n|${st:-stopped}|$ip"
done
'''
    try:
        rc, out = await deploy_mod._exec_on_node(
            dict(node), script, {"id":"import","log":[],"status":"","result":None}, 60)
    except Exception as e:
        raise HTTPException(500, f"读取宿主机 LXC 失败: {e}")
    imported = 0
    for line in out.splitlines():
        if not line.startswith("CT|"):
            continue
        parts = line.split("|")
        if len(parts) < 2:
            continue
        name = parts[1].strip()
        state = parts[2].strip().lower() if len(parts) > 2 else "stopped"
        ip = parts[3].strip() if len(parts) > 3 else ""
        if not name or db.one("SELECT id FROM containers WHERE name=?", (name,)):
            continue
        db.ex("""INSERT INTO containers(uuid,name,node_id,template,status,cpu,mem,disk,ip,note,created_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              uuidlib.uuid4().hex[:16], name, nid, "existing",
              "running" if state == "running" else "stopped",
              1, 512, 5, ip, "从宿主机导入", db.now())
        imported += 1
    db.audit(admin["sub"], "导入宿主机LXC", node["name"],
             f"导入 {imported} 个容器", request.client.host)
    return {"ok": True, "imported": imported, "output": out[-500:]}


# ────────────────────────── 节点 Swap 管理 ──────────────────────────
@router.get("/nodes/{nid}/swap")
async def node_swap_status(nid: int, user: dict = Depends(current_user)):
    """查看节点 swap 状态"""
    from . import deploy as deploy_mod
    node = _get_node(nid)
    if node["kind"] not in ("agent", "ssh"):
        raise HTTPException(400, "仅支持 Agent/SSH 节点")
    script = r'''
echo "=== SWAPINFO ==="
free -m | awk '/Swap:/{print "total_mb=" $2, "used_mb=" $3}'
echo "=== SWAPON ==="
swapon --show --noheadings 2>/dev/null || true
echo "=== SWAPPINESS ==="
cat /proc/sys/vm/swappiness 2>/dev/null
'''
    try:
        rc, out = await deploy_mod._exec_on_node(
            dict(node), script, {"id":"swap","log":[],"status":"","result":None}, 30)
    except Exception as e:
        raise HTTPException(500, f"读取 swap 状态失败: {e}")
    total_mb = 0
    used_mb = 0
    swappiness = 60
    files = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("total_mb="):
            # awk 输出形如 "total_mb=2048 used_mb=0"（同一行两字段）
            try:
                fields = line.split("=", 1)[1].split()
                total_mb = int(fields[0])
                for f in fields[1:]:
                    if f.startswith("used_mb="):
                        used_mb = int(f.split("=", 1)[1])
            except Exception:
                pass
        elif line.startswith("/"):
            # swapon --show --noheadings 输出列: NAME TYPE SIZE USED [PRIO]
            parts = line.split()
            if len(parts) >= 4 and parts[1] in ("file", "partition"):
                files.append({"path": parts[0], "size": parts[2], "used": parts[3]})
            elif len(parts) >= 2:
                files.append({"path": parts[0], "size": parts[1],
                              "used": parts[2] if len(parts) > 2 else ""})
        elif line.isdigit():
            swappiness = int(line)
    return {"total_mb": total_mb, "used_mb": used_mb, "swappiness": swappiness,
            "files": files, "raw": out[-500:]}


@router.post("/nodes/{nid}/swap")
async def node_swap_create(nid: int, body: SwapIn, request: Request,
                           admin: dict = Depends(require_admin)):
    """在宿主机创建/扩容 swap 文件"""
    from . import deploy as deploy_mod
    node = _get_node(nid)
    if node["kind"] not in ("agent", "ssh"):
        raise HTTPException(400, "仅支持 Agent/SSH 节点")
    size_gb = max(1, min(body.size_gb, 64))
    script = f'''
set -e
SWAPFILE=/swapfile
SIZE_GB={size_gb}
echo "==> [1/6] 检查磁盘空间"
AVAIL_MB=$(df -m / | awk 'NR==2{{print $4}}')
NEED_MB=$((SIZE_GB * 1024 + 1024))
echo "    可用 ${{AVAIL_MB}}MB，需要 ${{NEED_MB}}MB"
if [ "$AVAIL_MB" -lt "$NEED_MB" ]; then
  echo "ERROR: 磁盘空间不足，可用 ${{AVAIL_MB}}MB，需要 ${{NEED_MB}}MB"; exit 1
fi

echo "==> [2/6] 关闭已有 swapfile（如有）"
if swapon --show --noheadings 2>/dev/null | grep -q "^$SWAPFILE "; then
  swapoff "$SWAPFILE" 2>/dev/null || true
  echo "    已关闭旧 swap"
else
  echo "    无旧 swap，跳过"
fi

echo "==> [3/6] 创建 ${{SIZE_GB}}G swap 文件"
if command -v fallocate >/dev/null 2>&1; then
  echo "    使用 fallocate 快速分配..."
  fallocate -l ${{SIZE_GB}}G "$SWAPFILE"
else
  echo "    使用 dd 写入（较慢，请耐心等待）..."
  dd if=/dev/zero of="$SWAPFILE" bs=1M count=$((SIZE_GB*1024)) status=progress
fi
chmod 600 "$SWAPFILE"
echo "    文件已创建: $SWAPFILE ($(du -sh "$SWAPFILE" | cut -f1))"

echo "==> [4/6] 格式化 swap"
mkswap "$SWAPFILE"

echo "==> [5/6] 启用 swap"
swapon "$SWAPFILE"
echo "    已启用"

echo "==> [6/6] 写入 /etc/fstab 开机自启"
grep -q "^$SWAPFILE " /etc/fstab 2>/dev/null || echo "$SWAPFILE none swap sw 0 0" >> /etc/fstab
echo "    完成"

echo ""
echo "===== 当前 Swap 状态 ====="
free -h
swapon --show
'''
    try:
        rc, out = await deploy_mod._exec_on_node(
            dict(node), script, {"id":"swap","log":[],"status":"","result":None}, 300)
    except Exception as e:
        raise HTTPException(500, f"创建 swap 失败: {e}")
    if rc != 0:
        raise HTTPException(500, out[-800:])
    db.audit(admin["sub"], "创建Swap", node["name"], f"{size_gb}G", request.client.host)
    return {"ok": True, "output": out[-1500:]}


@router.delete("/nodes/{nid}/swap")
async def node_swap_delete(nid: int, request: Request, admin: dict = Depends(require_admin)):
    """删除宿主机 swap 文件"""
    from . import deploy as deploy_mod
    node = _get_node(nid)
    if node["kind"] not in ("agent", "ssh"):
        raise HTTPException(400, "仅支持 Agent/SSH 节点")
    script = r'''
SWAPFILE=/swapfile
if [ -f "$SWAPFILE" ] || swapon --show --noheadings 2>/dev/null | grep -q "$SWAPFILE"; then
  swapoff "$SWAPFILE" 2>/dev/null || true
  sed -i "\|^$SWAPFILE |d" /etc/fstab 2>/dev/null || true
  rm -f "$SWAPFILE"
  echo "swap removed"
else
  echo "no swapfile found"
fi
'''
    try:
        rc, out = await deploy_mod._exec_on_node(
            dict(node), script, {"id":"swap","log":[],"status":"","result":None}, 60)
    except Exception as e:
        raise HTTPException(500, f"删除 swap 失败: {e}")
    db.audit(admin["sub"], "删除Swap", node["name"], "", request.client.host)
    return {"ok": True, "output": out[-300:]}


# ────────────────────────── agent REST ──────────────────────────
from fastapi import Request as _Req
from fastapi.responses import PlainTextResponse, JSONResponse


@router.get("/agent/agent.py")
def agent_py(token: str = ""):
    return PlainTextResponse(agent_mod.AGENT_PY, media_type="text/x-python")


@router.get("/agent/install.sh")
def install_sh(request: _Req, token: str = "", api: str = ""):
    base = api or _panel_base(request)
    script = agent_mod.INSTALL_SH.replace("__API__", base).replace("__TOKEN__", token)
    return PlainTextResponse(script, media_type="text/x-shellscript")


@router.get("/agent/uninstall.sh")
def uninstall_sh():
    """Agent/探针 一键清理脚本（无需鉴权，脚本本身不含任何敏感信息）"""
    return PlainTextResponse(agent_mod.UNINSTALL_SH, media_type="text/x-shellscript")


def _agent_auth(request: _Req) -> int:
    """校验 Agent Bearer Token，返回 node_id"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ag_"):
        raise HTTPException(401, "bad agent")
    row = db.one("SELECT id FROM nodes WHERE agent_token=?", (auth[7:],))
    if not row:
        raise HTTPException(401, "unknown agent")
    return row["id"]


@router.post("/agent/poll")
async def agent_poll(request: _Req):
    nid = _agent_auth(request)
    try:
        report = await request.json()
    except Exception:
        report = {}
    agent_mod.touch(nid)
    monitor.agent_report(nid, report)
    # 如果接入时选择"作为母机"，且目标机未安装 LXC，自动下发一次安装命令（15分钟去重）
    node = db.one("SELECT * FROM nodes WHERE id=?", (nid,))
    if node and node["install_lxc"] and not node["lxc_ok"]:
        import time as _time
        import datetime as _dt
        last = node["lxc_install_ts"] or ""
        try:
            last_ts = _dt.datetime.strptime(last, "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            last_ts = 0
        if _time.time() - last_ts > 900:
            agent_mod.queue_exec(nid, nodes_mod.INSTALL_SH, timeout=900)
            db.ex("UPDATE nodes SET lxc_install_ts=? WHERE id=?", (db.now(), nid))
            db.audit("system", "自动安装LXC", node["name"], "agent接入后按需安装", "")
    cmds = agent_mod.pop_pending(nid)
    return {"commands": cmds}


@router.post("/agent/result")
async def agent_result(request: _Req):
    payload = await request.json()
    agent_mod.push_result(payload["id"], int(payload.get("rc", 0)),
                          base64_decode(payload.get("out", "")))
    return {"ok": True}


@router.post("/agent/pty_out")
async def agent_pty_out(request: _Req):
    """Agent PTY 输出回流（终端会话数据流）"""
    nid = _agent_auth(request)
    p = await request.json()
    agent_mod.pty_push(nid, str(p.get("sid", "")), int(p.get("seq") or 0),
                       str(p.get("data") or ""), bool(p.get("closed")))
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


# ────────────────────────── Agent 升级 / 远程诊断 ──────────────────────────
class ExecIn(BaseModel):
    script: str
    timeout: int = Field(60, ge=5, le=300)


@router.post("/nodes/{nid}/upgrade-agent")
async def node_upgrade_agent(nid: int, request: Request,
                             admin: dict = Depends(require_admin)):
    """向在线 Agent 下发自升级脚本（备份→下载面板最新版→校验→重启→失败自动回滚）"""
    node = _get_node(nid)
    if node["kind"] != "agent":
        raise HTTPException(400, "仅 Agent 节点支持")
    if not agent_mod.is_online(nid):
        raise HTTPException(409, "Agent 离线，无法下发升级命令")
    cid = agent_mod.queue_exec(nid, agent_mod.UPGRADE_SH, timeout=150)
    return {"ok": True, "queued": cid,
            "note": "已下发，服务数秒内自动重启，请稍后通过节点列表心跳确认恢复"}


@router.post("/agents/upgrade-all")
async def agents_upgrade_all(request: Request,
                             admin: dict = Depends(require_admin)):
    """批量升级所有在线 Agent 节点"""
    rows = db.q("SELECT id,name FROM nodes WHERE kind='agent'")
    queued, skipped = [], []
    for r in rows:
        if agent_mod.is_online(r["id"]):
            agent_mod.queue_exec(r["id"], agent_mod.UPGRADE_SH, timeout=150)
            queued.append({"id": r["id"], "name": r["name"]})
        else:
            skipped.append({"id": r["id"], "name": r["name"], "reason": "offline"})
    return {"ok": True, "queued_count": len(queued),
            "queued": queued, "skipped": skipped}


@router.post("/nodes/{nid}/exec")
async def node_exec_diag(nid: int, body: ExecIn, request: Request,
                         admin: dict = Depends(require_admin)):
    """在 Agent 节点上同步执行脚本并返回结果（运维诊断用，≤300s）"""
    node = _get_node(nid)
    if node["kind"] != "agent":
        raise HTTPException(400, "仅 Agent 节点支持")
    if not agent_mod.is_online(nid):
        raise HTTPException(409, "Agent 离线")
    import asyncio as _aio
    cid = agent_mod.queue_exec(nid, body.script, timeout=body.timeout)
    res = await _aio.to_thread(agent_mod.wait_result, cid, body.timeout + 15)
    if not res:
        raise HTTPException(504, "执行超时或连接中断")
    return {"rc": int(res.get("rc", 1)), "out": str(res.get("out", ""))[-8000:]}


# ────────────────────────── 一键部署 ──────────────────────────
class DeployIn(BaseModel):
    app_type: str
    start_port: int = Field(8881, ge=1024, le=65528)
    sni: str = ""
    target_type: str = Field("container", pattern="^(container|host)$")
    container_id: int | None = None
    node_id: int | None = None


@router.get("/apps/catalog")
def apps_catalog(user: dict = Depends(current_user)):
    return [{"type": k, **{kk: vv for kk, vv in v.items() if kk != "single"}}
            for k, v in deploy_mod.CATALOG.items()]


@router.get("/apps")
def list_apps(user: dict = Depends(current_user)):
    rows = db.q("""
        SELECT a.id, a.container_id, a.node_id, a.name, a.app_type, a.params,
               a.links, a.dnat_rules, a.status, a.created_at,
               c.name AS container, n.name AS node_name
        FROM apps a
        LEFT JOIN containers c ON c.id=a.container_id
        LEFT JOIN nodes n ON n.id=a.node_id
        ORDER BY a.id DESC""")
    out = []
    for r in rows:
        d = dict(r)
        try:
            params = json.loads(d["params"] or "{}")
        except Exception:
            params = {}
        try:
            d["spec"] = params.get("spec") or []
        except Exception:
            d["spec"] = []
        d["public_ip"] = params.get("public_ip", "")
        try:
            d["links"] = json.loads(d["links"] or "[]")
        except Exception:
            d["links"] = []
        try:
            d["dnat_rules"] = json.loads(d["dnat_rules"] or "[]")
        except Exception:
            d["dnat_rules"] = []
        d.pop("params", None)
        out.append(d)
    return out


@router.delete("/apps/{app_id}/nodes/{index}")
async def del_single_node(app_id: int, index: int, request: Request,
                          admin: dict = Depends(require_admin)):
    """删除某个应用中的单个代理节点（更新 sing-box 配置并移除端口映射）"""
    try:
        # 传完整 user 字典（remove_single_node 内部 audit 需要 user["sub"]；
        # 此前误传 admin["sub"] 字符串导致删除后 500）
        return await deploy_mod.remove_single_node(
            app_id, index, admin, request.client.host)
    except ValueError as e:
        raise HTTPException(404, str(e))


class SyncMachineIn(BaseModel):
    node_id: int | None = None
    container_id: int | None = None


@router.post("/apps/sync-machine")
async def sync_machine(body: SyncMachineIn, request: Request,
                       admin: dict = Depends(require_admin)):
    """按机器合并重建 sing-box 配置（用于修复多应用互相覆盖/协议不通）"""
    from . import deploy as deploy_mod
    if not body.node_id and not body.container_id:
        raise HTTPException(400, "请指定 node_id 或 container_id")
    node = None
    container = None
    if body.node_id:
        node = db.one("SELECT * FROM nodes WHERE id=?", (body.node_id,))
        if not node:
            raise HTTPException(404, "节点不存在")
    if body.container_id:
        container = db.one("SELECT * FROM containers WHERE id=?", (body.container_id,))
        if not container:
            raise HTTPException(404, "容器不存在")
        if not node:
            node = db.one("SELECT * FROM nodes WHERE id=?", (container["node_id"],))
    if not node:
        raise HTTPException(404, "节点不存在")
    try:
        ok = await deploy_mod._sync_machine_singbox(
            body.container_id, body.node_id or (container["node_id"] if container else 0),
            dict(node), dict(container) if container else None,
            {"id":"sync","log":[],"status":"","result":None})
    except Exception as e:
        raise HTTPException(500, str(e))
    db.audit(admin["sub"], "同步节点配置",
             (container or node)["name"], "", request.client.host)
    return {"ok": True, "synced": ok}


@router.post("/deploy")
async def deploy(body: DeployIn, request: Request, user: dict = Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "部署需要管理员权限")
    if body.target_type == "container" and not body.container_id:
        raise HTTPException(400, "缺少 container_id")
    if body.target_type == "host" and not body.node_id:
        raise HTTPException(400, "缺少 node_id")
    try:
        job_id = await deploy_mod.start_deploy(
            body.target_type, body.app_type,
            body.start_port, body.sni.strip() or "",
            user, request.client.host,
            container_id=body.container_id, node_id=body.node_id)
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


# ────────────────────────── 订阅中心 ──────────────────────────
@router.get("/sub/{token}")
def subscription(token: str, target: str = "", request: _Req = None):
    """公开订阅端点（对标 X-UI-Server /api/sub）
    · UA 含 clash/mihomo/stash/sing-box… 或 ?target=clash → Clash.Meta YAML
    · 否则 → base64(分享链接列表)
    """
    from . import subscribe as sub_mod
    real = sub_mod.get_or_create_sub_token()
    if not token or token != real:
        raise HTTPException(404, "Not found")
    ua = request.headers.get("user-agent", "") if request else ""
    body, ctype, disp = sub_mod.render_subscription(ua, target)
    headers = {"Cache-Control": "no-store",
               "subscription-userinfo": sub_mod.userinfo_header()}
    if disp:
        headers["Content-Disposition"] = disp
    return PlainTextResponse(body, media_type=ctype, headers=headers)


@router.get("/apps/sub-info")
def sub_info(request: Request, user: dict = Depends(current_user)):
    """面板内展示订阅地址（需登录）"""
    from . import subscribe as sub_mod
    tok = sub_mod.get_or_create_sub_token()
    base = _panel_base(request)
    n = len(sub_mod.collect_specs())
    return {
        "token": tok,
        "url": f"{base}/api/sub/{tok}",
        "clash_url": f"{base}/api/sub/{tok}?target=clash",
        "nodes": n,
        "traffic": sub_mod.get_sub_traffic(),
    }


@router.post("/apps/sub-reset")
def sub_reset(request: Request, admin: dict = Depends(require_admin)):
    """重置订阅 Token（旧链接立即失效）"""
    from . import subscribe as sub_mod
    tok = sub_mod.reset_sub_token()
    base = _panel_base(request)
    db.audit(admin["sub"], "重置订阅令牌", "system", "", request.client.host)
    return {"ok": True, "token": tok, "url": f"{base}/api/sub/{tok}"}


class SubTrafficIn(BaseModel):
    remaining_gb: float | None = None
    expire: str = ""


@router.get("/apps/sub-traffic")
def sub_traffic_get(admin: dict = Depends(require_admin)):
    """查看订阅流量显示设置"""
    from . import subscribe as sub_mod
    return sub_mod.get_sub_traffic()


@router.post("/apps/sub-traffic")
def sub_traffic_set(body: SubTrafficIn, request: Request, admin: dict = Depends(require_admin)):
    """流量重置：手动设定订阅显示的剩余流量（留空=9999G），可选到期日"""
    from . import subscribe as sub_mod
    sub_mod.set_sub_traffic(body.remaining_gb, (body.expire or "").strip())
    db.audit(admin["sub"], "设定订阅流量显示", "system", "", request.client.host)
    return {"ok": True, **sub_mod.get_sub_traffic()}


# ────────────────────────── 订阅转换（外部机场导入 / Clash ↔ V2Ray 互转） ──────────────────────────
class ConvIn(BaseModel):
    name: str = ""
    url: str = ""
    content: str = ""


class ConvPreviewIn(BaseModel):
    content: str


@router.get("/conv/sources")
def conv_sources(request: Request, user: dict = Depends(current_user)):
    """列出所有外部订阅转换源，附公开 Clash/V2Ray 链接"""
    from . import subconv as sc
    base = _panel_base(request)
    out = []
    for s in sc.list_sources():
        s["clash_url"] = f"{base}/api/conv/{s['token']}/clash"
        s["v2ray_url"] = f"{base}/api/conv/{s['token']}/v2ray"
        out.append(s)
    return out


@router.post("/conv/sources")
def conv_add(body: ConvIn, request: Request, user: dict = Depends(current_user)):
    """新增外部订阅：url（机场订阅链接）或 content（直接粘贴订阅内容）"""
    if not body.url.strip() and not body.content.strip():
        raise HTTPException(400, "url 和 content 至少填一个")
    from . import subconv as sc
    try:
        s = sc.add_source(body.name.strip(), body.url.strip(), body.content.strip())
    except Exception as e:
        raise HTTPException(400, f"添加失败: {e}")
    base = _panel_base(request)
    s["clash_url"] = f"{base}/api/conv/{s['token']}/clash"
    s["v2ray_url"] = f"{base}/api/conv/{s['token']}/v2ray"
    return s


@router.delete("/conv/sources/{sid}")
def conv_delete(sid: int, user: dict = Depends(current_user)):
    from . import subconv as sc
    sc.delete_source(sid)
    return {"ok": True}


@router.post("/conv/sources/{sid}/refresh")
def conv_refresh(sid: int, request: Request, user: dict = Depends(current_user)):
    from . import subconv as sc
    try:
        s = sc.refresh_source(sid)
    except KeyError:
        raise HTTPException(404, "订阅不存在")
    base = _panel_base(request)
    s["clash_url"] = f"{base}/api/conv/{s['token']}/clash"
    s["v2ray_url"] = f"{base}/api/conv/{s['token']}/v2ray"
    return s


@router.post("/conv/preview")
def conv_preview(body: ConvPreviewIn, user: dict = Depends(current_user)):
    """直接粘贴订阅文本，返回解析出的节点预览（不保存）"""
    from . import subconv as sc
    nodes = sc.parse_subscription_text(body.content)
    return {
        "node_count": len(nodes),
        "names": [n.get("name", "") for n in nodes[:60]],
        "clash": sc.build_clash_yaml(nodes, "NexPanel 转换预览")[:2000],
        "uris": [sc.to_uri(n) for n in nodes[:30]],
    }


@router.post("/conv/sources/{sid}/traffic")
def conv_traffic(sid: int, body: SubTrafficIn, user: dict = Depends(current_user)):
    """流量重置：手动设定该转换订阅显示的剩余流量（留空=9999G），可选到期日"""
    from . import subconv as sc
    try:
        sc.set_traffic(sid, body.remaining_gb, (body.expire or "").strip())
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.get("/conv/{token}/clash")
def conv_clash(token: str, request: _Req):
    """公开 Clash 订阅地址（随机 token 鉴权，无需登录）"""
    from fastapi.responses import PlainTextResponse
    from . import subconv as sc
    row = sc.get_source_by_token(token)
    if not row:
        raise HTTPException(404, "Not found")
    nodes = sc.node_uris(token, by_token=True)
    body = sc.build_clash_yaml(nodes, row["name"] or "NexPanel 转换")
    return PlainTextResponse(body, media_type="text/yaml; charset=utf-8",
                             headers={"Cache-Control": "no-store",
                                      "subscription-userinfo": sc.row_userinfo_header(row)})


@router.get("/conv/{token}/v2ray")
def conv_v2ray(token: str, request: _Req):
    """公开 Base64 URI 订阅地址（v2rayNG / Shadowrocket / NekoBox 等）"""
    from fastapi.responses import PlainTextResponse
    from . import subconv as sc
    row = sc.get_source_by_token(token)
    if not row:
        raise HTTPException(404, "Not found")
    nodes = sc.node_uris(token, by_token=True)
    body = sc.build_base64_uri(nodes)
    return PlainTextResponse(body, media_type="text/plain; charset=utf-8",
                             headers={"Cache-Control": "no-store",
                                      "subscription-userinfo": sc.row_userinfo_header(row)})


# ────────────────────────── 探针监控 ──────────────────────────
@router.get("/probes")
def probes(user: dict = Depends(current_user)):
    rows = [dict(r) for r in db.q(
        "SELECT * FROM nodes WHERE kind='agent' AND role='probe' ORDER BY id")]
    from . import agent as agent_mod
    out = []
    for r in rows:
        entry = monitor.get_cache(r["id"]) or {}
        host = entry.get("host") or {}
        online = agent_mod.is_online(r["id"])
        s = monitor.summary_of(r)
        mem_t = host.get("mem_total_mb", 0)
        out.append({"id": r["id"], "name": r["name"], "role": "probe",
                    "agent_token": r["agent_token"],
                    "status": s["status"],
                    "online": online,
                    "os": host.get("os") or r["os_info"] or "",
                    "hostname": host.get("hostname", ""),
                    "public_ip": r.get("public_ip") or host.get("hostname", ""),
                    "cpu_pct": host.get("cpu_pct", 0.0),
                    "cores": host.get("cores", 1),
                    "mem_total_mb": mem_t, "mem_used_mb": host.get("mem_used_mb", 0),
                    "disk_total_gb": host.get("disk_total_gb", 0),
                    "disk_used_gb": host.get("disk_used_gb", 0),
                    "rx_kbps": host.get("rx_kbps", 0), "tx_kbps": host.get("tx_kbps", 0),
                    "uptime_s": host.get("uptime_s", 0),
                    "load": host.get("load"),
                    "latency": entry.get("latency", {})})
    return out


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
                "nodes_online": sum(1 for s in summaries if s["status"] in ("online", "nolxc"))},
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
                                 "cpu", "mem", "swap", "disk", "ip", "note", "created_at")},
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
    db.ex("""INSERT INTO containers(uuid,name,node_id,template,status,cpu,mem,swap,disk,ip,note,created_at)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
          cid, name, node["id"], body.template, "stopped",
          body.cpu, body.mem, body.swap, body.disk, ip, body.note, db.now())
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


class ContainerConfigIn(BaseModel):
    cpu: int = Field(1, ge=1, le=16)
    mem: int = Field(512, ge=64, le=1048576, multiple_of=64)
    swap: int = Field(0, ge=0, le=1048576)
    disk: int = Field(5, ge=1, le=2048)


@router.put("/containers/{cid}/config")
async def update_container_config(cid: int, body: ContainerConfigIn, request: Request,
                                  admin: dict = Depends(require_admin)):
    """修改已创建 LXC 的配置（需先停止容器）"""
    row = db.one("SELECT * FROM containers WHERE id=?", (cid,))
    if not row:
        raise HTTPException(404, "实例不存在")
    c = dict(row)
    if c["status"] == "running":
        raise HTTPException(400, "请先停止容器再修改配置")
    node = _get_node(c["node_id"]) if c["node_id"] else None
    if not node or node["kind"] == "demo":
        raise HTTPException(400, "该实例不支持修改配置")

    # 更新数据库
    db.ex("UPDATE containers SET cpu=?, mem=?, swap=?, disk=? WHERE id=?",
          (body.cpu, body.mem, body.swap, body.disk, cid))

    # 同步到 LXC 配置文件（agent/ssh 节点）
    if node["kind"] in ("agent", "ssh"):
        from . import deploy as deploy_mod
        mem_bytes = body.mem * 1024 * 1024
        swap_bytes = body.swap * 1024 * 1024 if body.swap > 0 else 0
        cpu_quota = body.cpu * 100000
        script = f'''
NAME="{c['name']}"
CONFIG="/var/lib/lxc/$NAME/config"
if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY'
name = "{c['name']}"
cfg = f"/var/lib/lxc/{{name}}/config"
mem = {mem_bytes}
swap = {swap_bytes}
cpu = {cpu_quota}
try:
    lines = open(cfg).read().splitlines()
except Exception:
    lines = []
out = []
mem_set = cpu_set = swap_set = False
for ln in lines:
    if ln.startswith('lxc.cgroup2.memory.max'):
        out.append(f'lxc.cgroup2.memory.max = {{mem}}'); mem_set = True
    elif ln.startswith('lxc.cgroup2.memory.swap.max'):
        if swap > 0:
            out.append(f'lxc.cgroup2.memory.swap.max = {{swap}}'); swap_set = True
        # swap=0 时删除该行，恢复 LXC 默认 swap 行为
    elif ln.startswith('lxc.cgroup2.cpu.max'):
        out.append(f'lxc.cgroup2.cpu.max = {{cpu}} 100000'); cpu_set = True
    else:
        out.append(ln)
if not mem_set: out.append(f'lxc.cgroup2.memory.max = {{mem}}')
if not cpu_set: out.append(f'lxc.cgroup2.cpu.max = {{cpu}} 100000')
if swap > 0 and not swap_set: out.append(f'lxc.cgroup2.memory.swap.max = {{swap}}')
open(cfg, 'w').write('\n'.join(out) + '\n')
PY
else
  echo "no python3, skip lxc config sync"
fi
'''
        try:
            await deploy_mod._exec_on_node(dict(node), script,
                                           {"id":"cfg","log":[],"status":"","result":None}, 60)
        except Exception:
            pass  # 远端同步失败不阻塞，DB 已更新

    db.audit(admin["sub"], "修改配置", c["name"],
             f"{body.cpu}C/{body.mem}M/{body.swap}Swap/{body.disk}G", request.client.host)
    return {"ok": True}


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

    # 清理部署在该容器上的应用（容器已删除，远端配置已不存在，直接清 DB）
    app_ids = [r["id"] for r in db.q("SELECT id FROM apps WHERE container_id=?", (cid,))]
    if app_ids:
        ph = ",".join("?" * len(app_ids))
        db.ex(f"DELETE FROM subscription_limits WHERE app_id IN ({ph})", *app_ids)
        db.ex(f"DELETE FROM apps WHERE id IN ({ph})", *app_ids)

    db.ex("DELETE FROM containers WHERE id=?", (cid,))
    db.audit(user["sub"], "删除实例", c["name"],
             f"同时清理 {len(app_ids)} 个应用" if app_ids else "", request.client.host)
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


# ═══════════════════════ 通知告警(TG) ═══════════════════════
@router.get("/notify/settings")
def notify_settings(user: dict = Depends(current_user)):
    from . import notify as notify_mod
    return notify_mod.get_settings()


@router.post("/notify/settings")
def notify_save(body: dict, request: Request, admin: dict = Depends(require_admin)):
    from . import notify as notify_mod
    bot_token = (body.get("bot_token") or "").strip()
    chat_id = (body.get("chat_id") or "").strip()
    enabled = bool(body.get("enabled", False))
    events = (body.get("events") or "node_offline,container_crash").strip()
    notify_mod.save_settings(bot_token, chat_id, enabled, events)
    db.audit(admin["sub"], "修改通知设置", "system", "", request.client.host)
    return {"ok": True}


@router.post("/notify/test")
def notify_test(body: dict, request: Request, user: dict = Depends(current_user)):
    from . import notify as notify_mod
    # 临时用请求中的配置发一条测试消息
    bot_token = (body.get("bot_token") or "").strip()
    chat_id = (body.get("chat_id") or "").strip()
    if not bot_token or not chat_id:
        raise HTTPException(400, "请先填写 Bot Token 和 Chat ID")
    # 保存原配置，发送后恢复
    old_cfg = notify_mod.get_settings()
    notify_mod.save_settings(bot_token, chat_id, True, "all")
    ok = notify_mod.send_telegram(
        "<b>🔔 NexPanel 测试消息</b>\n"
        f"如果您收到此消息，说明 Telegram 告警配置正确！\n"
        f"<i>{db.now()}</i>")
    # 恢复原配置
    notify_mod.save_settings(old_cfg["bot_token"], old_cfg["chat_id"],
                             old_cfg["enabled"], old_cfg["events"])
    if not ok:
        raise HTTPException(400, "发送失败，请检查 Bot Token 和 Chat ID 是否正确")
    return {"ok": True, "message": "测试消息已发送，请检查 Telegram"}


# ═══════════════════════ 备份 / 恢复 ═══════════════════════
@router.get("/backup/settings")
def backup_settings(user: dict = Depends(current_user)):
    from . import backup as backup_mod
    return backup_mod.get_settings()


@router.post("/backup/settings")
def backup_save(body: dict, request: Request, admin: dict = Depends(require_admin)):
    from . import backup as backup_mod

    def _int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    data = {
        "backup_enabled": "1" if body.get("enabled", False) else "0",
        "backup_interval_hours": str(_int(body.get("interval_hours"), 24)),
        "backup_type": str(body.get("type", "s3")),
        "backup_endpoint": (body.get("endpoint") or "").strip(),
        "backup_region": (body.get("region") or "us-east-1").strip(),
        "backup_bucket": (body.get("bucket") or "nexpanel-backup").strip(),
        "backup_access_key": (body.get("access_key") or "").strip(),
        "backup_secret_key": (body.get("secret_key") or "").strip(),
        "backup_retention_days": str(_int(body.get("retention_days"), 30)),
    }
    backup_mod.save_settings(data)
    db.audit(admin["sub"], "修改备份设置", "system", "", request.client.host)
    return {"ok": True}


@router.post("/backup/run")
def backup_run(request: Request, admin: dict = Depends(require_admin)):
    """立即执行一次备份"""
    from . import backup as backup_mod
    import asyncio
    try:
        result = backup_mod.do_backup()
        if result != "ok":
            raise HTTPException(500, f"备份失败: {result}")
        db.audit(admin["sub"], "手动备份", "system", "成功", request.client.host)
        return {"ok": True, "message": "备份完成"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"备份异常: {e}")


@router.post("/backup/restore")
async def backup_restore(request: Request, admin: dict = Depends(require_admin)):
    """从上传的备份文件恢复数据库"""
    from . import backup as backup_mod
    import tempfile
    import shutil
    import pathlib

    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(400, "请上传备份文件")

    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        content = await file.read()
        with open(tmp.name, "wb") as f:
            f.write(content)

        result = backup_mod.restore_from_backup(tmp.name)
        if result != "ok":
            raise HTTPException(500, f"恢复失败: {result}")

        db.audit(admin["sub"], "从备份恢复", "system", f"文件: {file.filename}", request.client.host)
        return {"ok": True, "message": "数据库已从备份恢复，建议重启面板"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"恢复异常: {e}")
    finally:
        if tmp:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass


# ═══════════════════════ 流量统计 ═══════════════════════
@router.get("/traffic/nodes")
def traffic_nodes(user: dict = Depends(current_user)):
    from . import traffic as traffic_mod
    return traffic_mod.get_all_traffic(days=30)


@router.get("/traffic/node/{node_id}")
def traffic_node(node_id: int, days: int = 30, user: dict = Depends(current_user)):
    from . import traffic as traffic_mod
    # 验证节点存在
    row = db.one("SELECT id FROM nodes WHERE id=?", (node_id,))
    if not row:
        raise HTTPException(404, "节点不存在")
    return traffic_mod.get_node_traffic(node_id, days)


@router.get("/traffic/daily")
def traffic_daily(date: str = "", user: dict = Depends(current_user)):
    """获取指定日期的流量汇总"""
    from . import traffic as traffic_mod
    if not date:
        from datetime import datetime
        date = datetime.now().strftime("%Y-%m-%d")
    rows = db.q("SELECT t.node_id, n.name, t.rx_bytes, t.tx_bytes "
                "FROM traffic_daily t LEFT JOIN nodes n ON n.id = t.node_id "
                "WHERE t.date=? ORDER BY t.rx_bytes + t.tx_bytes DESC", date)
    return [dict(r) for r in rows]


# ═══════════════════════ 订阅限额 ═══════════════════════
@router.get("/subscription/limits")
def subscription_limits(user: dict = Depends(current_user)):
    """获取全部应用的订阅限额"""
    from . import traffic as traffic_mod
    result = []
    for app in db.q("SELECT id, name, app_type FROM apps ORDER BY id"):
        limit = traffic_mod.get_subscription_limit(app["id"])
        limit["app_name"] = app["name"]
        limit["app_type"] = app["app_type"]
        # 检查状态
        status = traffic_mod.check_subscription_status(app["id"])
        limit["status"] = status.get("ok", True)
        limit["status_reason"] = status.get("reason", "")
        if status.get("warnings"):
            limit["warnings"] = status["warnings"]
        # 流量使用情况
        used = traffic_mod.aggregate_app_traffic(app["id"])
        limit["used_mb"] = used["total_mb"]
        limit["reset_at"] = used["reset_at"]
        result.append(limit)
    return result


@router.get("/subscription/limit/{app_id}")
def subscription_limit(app_id: int, user: dict = Depends(current_user)):
    from . import traffic as traffic_mod
    app = db.one("SELECT id, name, app_type FROM apps WHERE id=?", (app_id,))
    if not app:
        raise HTTPException(404, "应用不存在")
    limit = traffic_mod.get_subscription_limit(app_id)
    limit["app_name"] = app["name"]
    limit["app_type"] = app["app_type"]
    status = traffic_mod.check_subscription_status(app_id)
    limit["status"] = status.get("ok", True)
    limit["status_reason"] = status.get("reason", "")
    if status.get("warnings"):
        limit["warnings"] = status["warnings"]
    used = traffic_mod.aggregate_app_traffic(app_id)
    limit["used_mb"] = used["total_mb"]
    limit["reset_at"] = used["reset_at"]
    return limit


@router.post("/subscription/limit/{app_id}")
def subscription_set_limit(app_id: int, body: dict, request: Request,
                           admin: dict = Depends(require_admin)):
    from . import traffic as traffic_mod
    app = db.one("SELECT id, name FROM apps WHERE id=?", (app_id,))
    if not app:
        raise HTTPException(404, "应用不存在")
    traffic_limit_mb = int(body.get("traffic_limit_mb", 0))
    bandwidth_limit_kbps = int(body.get("bandwidth_limit_kbps", 0))
    expire_at = (body.get("expire_at") or "").strip()
    notes = (body.get("notes") or "").strip()
    limit = traffic_mod.set_subscription_limit(
        app_id, traffic_limit_mb, bandwidth_limit_kbps, expire_at, notes)
    db.audit(admin["sub"], "修改订阅限额", app["name"],
             f"流量: {traffic_limit_mb}MB, 过期: {expire_at}", request.client.host)
    return limit


@router.get("/subscription/stats")
def subscription_stats(user: dict = Depends(current_user)):
    """订阅总体统计"""
    from . import traffic as traffic_mod
    total_apps = db.one("SELECT COUNT(*) n FROM apps")["n"]
    limited_apps = db.one("SELECT COUNT(*) n FROM subscription_limits")["n"]
    over_limit = 0
    for app in db.q("SELECT id FROM apps"):
        status = traffic_mod.check_subscription_status(app["id"])
        if not status.get("ok", True):
            over_limit += 1
    return {
        "total_apps": total_apps,
        "limited_apps": limited_apps,
        "over_limit": over_limit,
    }


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
