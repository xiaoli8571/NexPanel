"""多节点监控：每个节点一个后台采集协程，结果写入内存缓存供 API 聚合"""
import asyncio
import time

from . import db, nodes as nodes_mod
from .lxc import DemoRuntime

CACHE: dict[int, dict] = {}          # node_id -> 采集缓存条目
_prev: dict[int, dict] = {}          # node_id -> 上次采样原始值(做差用)
_demo_runtimes: dict[int, DemoRuntime] = {}
_tasks: dict[int, asyncio.Task] = {}


def demo_runtime(node_id: int) -> DemoRuntime:
    return _demo_runtimes.setdefault(node_id, DemoRuntime())


# ────────────────── SSH 真实节点循环 ──────────────────
async def _ssh_loop(node: dict):
    nid = node["id"]
    while True:
        t0 = time.time()
        try:
            rc, out = await asyncio.to_thread(nodes_mod.run_cmd, node, nodes_mod.COLLECT_SH, 45)
            dt = max(time.time() - t0, 0.5)
            prev = _prev.setdefault(nid, {})
            CACHE[nid] = nodes_mod.parse_collect(out, prev, dt)
            status = CACHE[nid]["status"]
            if status in ("online", "nolxc"):
                lxc_ok = 1 if status == "online" else 0
                os_info = CACHE[nid]["host"]["os"] if CACHE[nid].get("host") else ""
                db.ex("UPDATE nodes SET status=?, lxc_ok=?, os_info=? WHERE id=?",
                      ("online" if status == "online" else "nolxc", lxc_ok, os_info, nid))
        except Exception as e:
            CACHE[nid] = {"status": "offline", "error": str(e)[:200],
                          "updated": time.time(), "host": None, "cts": {}}
            db.ex("UPDATE nodes SET status='offline' WHERE id=?", (nid,))
        await asyncio.sleep(3)


# ────────────────── 演示节点循环 ──────────────────
async def _demo_loop(node: dict):
    nid = node["id"]
    rt = demo_runtime(nid)
    while True:
        try:
            rows = [dict(r) for r in db.q(
                "SELECT name,status,cpu,mem FROM containers WHERE node_id=?", (nid,))]
            rt.step(rows)
            running = [r for r in rows if r["status"] == "running"]
            cts = {}
            mem_used = sum(rt.live(r)["mem_used_mb"] for r in running)
            cpu_sum = sum(rt.live(r)["cpu_pct"] for r in running)
            cores = 4
            for r in rows:
                live = rt.live(r)
                cts[r["name"]] = {"state": r["status"], "uptime_s": live["uptime_s"],
                                  "mem_used_mb": live["mem_used_mb"],
                                  "cpu_pct": live["cpu_pct"], "ip": ""}
            CACHE[nid] = {"status": "online", "error": "", "updated": time.time(),
                          "cts": cts,
                          "host": {"os": "Demo Runtime", "kernel": "simulated",
                                   "cores": cores, "hostname": node["name"],
                                   "cpu_pct": round(min(cpu_sum / cores, 100), 1),
                                   "mem_total_mb": 4096,
                                   "mem_used_mb": int(mem_used + 512),
                                   "disk_total_gb": 40.0,
                                   "disk_used_gb": round(sum(
                                       (c["disk"] or 5) * .21 for c in rows) + 4, 1),
                                   "rx_kbps": round(sum(rt.live(r)["rx_kbps"] for r in running), 1),
                                   "tx_kbps": round(sum(rt.live(r)["tx_kbps"] for r in running), 1)}}
        except Exception as e:
            CACHE[nid] = {"status": "offline", "error": str(e)[:200],
                          "updated": time.time(), "host": None, "cts": {}}
        await asyncio.sleep(1)


# ────────────────── 生命周期管理 ──────────────────
def start_node(node_row: dict):
    nid = node_row["id"]
    stop_node(nid)
    target = _demo_loop if node_row["kind"] == "demo" else _ssh_loop

    if _MAIN_LOOP and _MAIN_LOOP.is_running():
        # 请求线程：把任务调度回主事件循环
        asyncio.run_coroutine_threadsafe(_spawn_on(target, node_row), _MAIN_LOOP)
    else:
        # 启动阶段（lifespan 内）：当前线程即主循环
        _tasks[nid] = asyncio.get_running_loop().create_task(target(dict(node_row)))


_MAIN_LOOP: asyncio.AbstractEventLoop | None = None


async def _spawn_on(target, node_row: dict):
    nid = node_row["id"]
    _tasks[nid] = asyncio.get_running_loop().create_task(target(node_row))


def set_main_loop(loop: asyncio.AbstractEventLoop):
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def stop_node(node_id: int):
    task = _tasks.pop(node_id, None)
    if task:
        task.cancel()
    CACHE.pop(node_id, None)
    _prev.pop(node_id, None)


def start_all():
    global _MAIN_LOOP
    _MAIN_LOOP = asyncio.get_running_loop()
    for row in db.q("SELECT * FROM nodes"):
        if row["kind"] != "agent":
            start_node(row)
        else:
            touch_from_db(row)   # 恢复 last_seen 显示


def touch_from_db(row):
    from datetime import datetime
    try:
        ts = datetime.strptime(row["last_seen"], "%Y-%m-%d %H:%M:%S").timestamp()
        from . import agent as agent_mod
        agent_mod._live[row["id"]] = ts
    except Exception:
        pass


async def shutdown():
    for tid in list(_tasks):
        stop_node(tid)


def get_cache(node_id: int) -> dict | None:
    entry = CACHE.get(node_id)
    if not entry:
        return None
    # 数据过期判定（SSH 节点 20s 未更新视为离线）
    if entry["status"] == "online" and node_id in _tasks and \
       time.time() - entry["updated"] > 20 and _tasks[node_id].get_name() != "demo":
        pass  # 保留最近一次数据，状态由循环自身维护
    return entry


def container_live(c: dict) -> dict:
    """容器实时指标：优先取所属节点缓存"""
    entry = get_cache(c["node_id"])
    if entry and c["name"] in entry["cts"]:
        ct = entry["cts"][c["name"]]
        running = ct["state"] == "running"
        return {"cpu_pct": ct["cpu_pct"] if running else 0,
                "mem_used_mb": ct["mem_used_mb"] if running else 0,
                "rx_kbps": 0, "tx_kbps": 0,
                "ip": ct.get("ip", ""),
                "uptime_s": ct["uptime_s"] if running else 0}
    # 演示节点兜底（缓存尚未建立时）
    rt = _demo_runtimes.get(c["node_id"])
    if rt:
        d = rt.live(c); d["ip"] = c.get("ip") or ""; return d
    return {"cpu_pct": 0, "mem_used_mb": 0, "rx_kbps": 0, "tx_kbps": 0,
            "ip": c.get("ip") or "", "uptime_s": 0}


def summary_of(node_row: dict) -> dict:
    entry = get_cache(node_row["id"]) or {}
    host = entry.get("host") or {}
    counts = {"total": 0, "running": 0}
    for r in db.q("SELECT status FROM containers WHERE node_id=?", (node_row["id"],)):
        counts["total"] += 1
        counts["running"] += 1 if r["status"] == "running" else 0
    is_agent = node_row["kind"] == "agent"
    agent_ok = agent_online(node_row["id"]) if is_agent else False
    status = ("online" if agent_ok else "offline") if is_agent else \
             entry.get("status", node_row["status"] or "unknown")
    nrow = dict(node_row)
    return {"id": nrow["id"], "name": nrow["name"], "kind": nrow["kind"],
            "role": nrow.get("role") or "manage",
            "host_addr": f"{nrow['host']}:{nrow['port']}" if nrow["kind"] == "ssh" else "",
            "username": nrow["username"],
            "status": status,
            "error": entry.get("error", ""),
            "os_info": host.get("os") or node_row["os_info"] or "",
            "lxc_ok": (agent_ok and bool(host)) if is_agent else
                      (bool(host) and entry.get("status") == "online"),
            "live": {"cpu_pct": host.get("cpu_pct", 0.0),
                     "mem_total_mb": host.get("mem_total_mb", 0),
                     "mem_used_mb": host.get("mem_used_mb", 0),
                     "disk_total_gb": host.get("disk_total_gb", 0),
                     "disk_used_gb": host.get("disk_used_gb", 0),
                     "rx_kbps": host.get("rx_kbps", 0),
                     "tx_kbps": host.get("tx_kbps", 0)},
            "counts": counts}


# ────────────────── Agent 节点支撑 ──────────────────
def agent_online(node_id: int) -> bool:
    from . import agent as agent_mod
    return agent_mod.is_online(node_id)


def agent_report(node_id: int, report: dict):
    """Agent 心跳/指标 → 写入统一缓存（与 SSH 采集同构）"""
    sysinfo = report.get("sys") or {}
    host = report.get("host") or {}
    cts = report.get("cts") or {}
    entry = {
        "status": "online", "error": "", "updated": time.time(),
        "latency": report.get("latency") or {},
        "cts": {n: {"state": c.get("state", "stopped"),
                    "uptime_s": c.get("uptime_s", 0),
                    "mem_used_mb": c.get("mem_used_mb", 0),
                    "cpu_pct": c.get("cpu_pct", 0.0),
                    "ip": c.get("ip", "")} for n, c in cts.items()},
        "host": {"os": sysinfo.get("os", "Linux"),
                 "kernel": sysinfo.get("kernel", ""),
                 "cores": sysinfo.get("cores", 1),
                 "hostname": sysinfo.get("hostname", ""),
                 "cpu_pct": host.get("cpu_pct", 0.0),
                 "mem_total_mb": host.get("mem_total_mb", 0),
                 "mem_used_mb": host.get("mem_used_mb", 0),
                 "disk_total_gb": host.get("disk_total_gb", 0),
                 "disk_used_gb": host.get("disk_used_gb", 0),
                 "rx_kbps": host.get("rx_kbps", 0),
                 "tx_kbps": host.get("tx_kbps", 0),
                 "load": host.get("load"),
                 "uptime_s": host.get("uptime_s", 0)},
    }
    CACHE[node_id] = entry
    try:
        db.ex("UPDATE nodes SET status='online', os_info=?, public_ip=COALESCE(NULLIF(?,''),public_ip), last_seen=? WHERE id=?",
              (sysinfo.get("os", ""), sysinfo.get("public_ip", ""), db_now_str(), node_id))
    except Exception:
        pass


def db_now_str():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
