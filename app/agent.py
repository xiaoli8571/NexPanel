"""Agent 体系：
* AGENT_PY   部署到目标 VPS 的常驻代理(纯标准库, HTTP 轮询, 无依赖)
* 面板侧     待下发命令队列 / 结果回收 / 心跳指标入缓存 / PTY 终端流转发
"""
import asyncio
import base64
import secrets
import subprocess
import time

# Agent 脚本版本指纹：AGENT_PY 内嵌同名标记 + UPGRADE_SH 校验用，两处必须一致。
# 升级校验依赖它判断下载到的新版 agent.py 确实比已装版本新（防拿到错误页/旧缓存）。
AGENT_VER = "v20260908c"

# 长轮询窗口：面板在没有待下发命令时最多 hold 住这么久（秒）。
# 终端会话的按键/开控制台命令因此在「已挂起的那次请求」上即时返回，
# 输入侧延迟从「最多一个轮询周期」降到「≈1 个 RTT」。须 < agent 侧 poll 超时(12s)。
# 空闲窗口取 3s：配合 agent 侧 0.3s 的间隔，命令"没被挂起请求覆盖"的空窗只有 0.3s
# （点开控制台要等的那一下就是原来 1.5s 空窗造成的），而总请求频率与旧版持平。
POLL_HOLD = 2.0
POLL_HOLD_IDLE = 3.0

# ────────────────────────── 面板侧状态 ──────────────────────────
_pending: dict[int, list] = {}       # node_id -> [cmd,...]
_results: dict[str, dict] = {}       # cmd_id -> {"rc":..,"out":..} / event style
_live: dict[int, float] = {}         # node_id -> last_seen ts (ws/http 均可)
_token_nid: dict[str, int] = {}      # agent_token -> node_id（省掉每次 HTTP 的 SQLite 查询）

# ── PTY 终端会话（浏览器 ⇄ 面板 ⇄ Agent 轮询流） ──
_pty_subs: dict[str, asyncio.Queue] = {}   # sid -> 输出队列 (str chunk / "__CLOSED__")
_pty_node: dict[str, int] = {}             # sid -> node_id (校验 pty_out 归属)
_pty_recent: dict[int, float] = {}         # node_id -> 最近一次终端活动时间(开/输入/缩放/关闭)
_cmd_waits: dict[int, tuple] = {}          # node_id -> (loop, asyncio.Event) 长轮询唤醒


def _signal(node_id: int):
    """命令入队后唤醒该节点正挂起的长轮询（可能来自工作线程，故走 call_soon_threadsafe）"""
    ent = _cmd_waits.get(node_id)
    if not ent:
        return
    loop, ev = ent
    try:
        if loop.is_closed():
            return
        loop.call_soon_threadsafe(ev.set)
    except Exception:
        pass


def pty_active(node_id: int, grace: float = 15.0) -> bool:
    """该节点是否有终端会话（含刚关闭 15s 内：让 pty_close 也能即时下发，别留一个挂死的 shell）"""
    if any(nid == node_id for nid in _pty_node.values()):
        return True
    return (time.time() - _pty_recent.get(node_id, 0.0)) < grace


async def poll_commands(node_id: int, hold: float) -> list:
    """取待下发命令；为空时最多挂起 hold 秒，一有新命令立刻返回（长轮询）"""
    cmds = pop_pending(node_id)
    if cmds or hold <= 0:
        return cmds
    loop = asyncio.get_running_loop()
    ev = asyncio.Event()
    _cmd_waits[node_id] = (loop, ev)
    try:
        cmds = pop_pending(node_id)          # 注册后再查一次，避免注册竞态丢命令
        if not cmds:
            try:
                await asyncio.wait_for(ev.wait(), timeout=hold)
            except Exception:                # 含 TimeoutError / 连接中断
                pass
            cmds = pop_pending(node_id)
    finally:
        if _cmd_waits.get(node_id) == (loop, ev):
            _cmd_waits.pop(node_id, None)
    return cmds


def node_id_by_token(token: str) -> int | None:
    """agent_token -> node_id 内存缓存：终端会话期间请求很密集，不必每次打 SQLite"""
    return _token_nid.get(token)


def remember_token(token: str, node_id: int):
    if len(_token_nid) > 512:                # 防无界增长（token 轮换 / 节点删除后的残留）
        _token_nid.clear()
    _token_nid[token] = node_id


def forget_token(node_id: int | None = None):
    if node_id is None:
        _token_nid.clear()
        return
    for k in [k for k, v in _token_nid.items() if v == node_id]:
        _token_nid.pop(k, None)


def forget_node(node_id: int):
    """节点被删除时清掉它的全部面板侧残留。
    尤其重要：token 缓存若不清，已删节点的 Agent 仍能拿旧 token 通过鉴权。"""
    forget_token(node_id)
    _pending.pop(node_id, None)
    _live.pop(node_id, None)
    _pty_recent.pop(node_id, None)
    _cmd_waits.pop(node_id, None)
    for sid in [s for s, n in _pty_node.items() if n == node_id]:
        _pty_node.pop(sid, None)
        _pty_subs.pop(sid, None)



def open_pty(node_id: int, cmd: str, cols: int = 120, rows: int = 32) -> str:
    """在目标 Agent 上开启 PTY 会话，返回 sid"""
    sid = "p" + secrets.token_hex(8)
    _pty_subs[sid] = asyncio.Queue(maxsize=2000)
    _pty_node[sid] = node_id
    _pty_recent[node_id] = time.time()
    _pending.setdefault(node_id, []).append(
        {"id": "o" + secrets.token_hex(6), "op": "pty_open", "sid": sid,
         "cmd": cmd, "cols": max(40, min(cols, 500)), "rows": max(8, min(rows, 300))})
    _signal(node_id)
    return sid


def pty_input(sid: str, data: str):
    nid = _pty_node.get(sid)
    if nid is not None:
        _pending.setdefault(nid, []).append(
            {"id": "i" + secrets.token_hex(6), "op": "pty_in", "sid": sid,
             "data": base64.b64encode(data.encode("utf-8", errors="replace")).decode()})
        _pty_recent[nid] = time.time()
        _signal(nid)


def pty_resize(sid: str, cols: int, rows: int):
    nid = _pty_node.get(sid)
    if nid is not None:
        _pending.setdefault(nid, []).append(
            {"id": "w" + secrets.token_hex(6), "op": "pty_win", "sid": sid,
             "cols": max(40, min(cols, 500)), "rows": max(8, min(rows, 300))})
        _pty_recent[nid] = time.time()
        _signal(nid)


def close_pty(sid: str):
    """通知 Agent 关闭 PTY 并清理面板侧状态"""
    nid = _pty_node.pop(sid, None)
    q = _pty_subs.pop(sid, None)
    if nid is not None:
        _pending.setdefault(nid, []).append(
            {"id": "x" + secrets.token_hex(6), "op": "pty_close", "sid": sid})
        _pty_recent[nid] = time.time()
        _signal(nid)


def pty_push(node_id: int, sid: str, seq: int, data_b64: str, closed: bool) -> bool:
    """Agent 上报输出 → 推入订阅队列；返回 sid 是否仍有效"""
    if _pty_subs.get(sid) is None or _pty_node.get(sid) != node_id:
        return False
    q = _pty_subs[sid]
    try:
        if closed and seq == 0:
            return True                      # 未知会话的关闭包，忽略
        text = base64.b64decode(data_b64.encode()).decode("utf-8", errors="replace")
        if q.full():
            q.get_nowait()                   # 丢弃最旧，防止内存膨胀
        q.put_nowait(text)
        if closed:
            q.put_nowait("__CLOSED__")
        return True
    except Exception:
        return False


def new_token() -> str:
    return "ag_" + secrets.token_urlsafe(24)


def queue_exec(node_id: int, script: str, timeout: int = 120, b64: bool = True) -> str:
    cid = "c" + secrets.token_hex(8)
    _pending.setdefault(node_id, []).append(
        {"id": cid, "op": "exec", "b64": b64,
         "script": base64.b64encode(script.encode()).decode() if b64 else script,
         "timeout": timeout})
    _signal(node_id)
    return cid


def wait_result(cmd_id: str, timeout: float = 300) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cmd_id in _results:
            return _results.pop(cmd_id)
        time.sleep(0.05)
    _discard(_pending_scan(cmd_id))
    return None


def _pending_scan(cid):
    for nid, lst in _pending.items():
        for c in lst:
            if c["id"] == cid:
                return (nid, c)
    return None


def _discard(pair):
    if not pair:
        return
    try:
        _pending[pair[0]].remove(pair[1])
    except Exception:
        pass


def pop_pending(node_id: int) -> list:
    return _pending.pop(node_id, [])


def push_result(cmd_id: str, rc: int, out: str):
    # 自动安装 LXC / 升级等命令的结果没有 wait 方消费，按时间淘汰防止无限增长
    now = time.time()
    if len(_results) > 256:
        for k in [k for k, v in _results.items() if now - v.get("ts", 0) > 600]:
            _results.pop(k, None)
        if len(_results) >= 256:   # 突发洪峰：仍超限则按时间丢最老的
            for k in sorted(_results, key=lambda k: _results[k].get("ts", 0))[:len(_results) - 255]:
                _results.pop(k, None)
    _results[cmd_id] = {"rc": rc, "out": out, "ts": now}


def touch(node_id: int):
    _live[node_id] = time.time()


def is_online(node_id: int, max_age: int = 20) -> bool:
    ts = _live.get(node_id)
    return bool(ts and time.time() - ts < max_age)


def offline_nodes():
    return [nid for nid in _live if not is_online(nid)]


# ══════════════ 目标机上运行的 Agent（单文件、零依赖） ══════════════
AGENT_PY = r'''#!/usr/bin/env python3
"""NexPanel Agent — 反向接入面板，零依赖(HTTP 轮询)。安装即接管。"""
# 注意：http.client 必须起别名！本文件下面有 def http(...) 会遮蔽同名模块，
# 直接 `import http.client` 会让 http 变成函数 → 'function' object has no attribute 'client'
import base64, json, os, platform, socket, ssl, subprocess, sys, threading, time
import http.client as _http_client
import urllib.request
from urllib.parse import urlparse

API, TOKEN = "", ""
AGENT_VER = "v20260908c"   # 版本指纹：面板 UPGRADE_SH 校验用，改代码时同步更新
CONF = "/opt/lxcdeck-agent/agent.conf"
PREV = {"cpu_line": None, "rx": None, "tx": None, "ct_cpu": {}}
_last_full = 0.0
_cache_report = {}
_TLS = threading.local()          # 每个线程一条常驻 HTTP(S) 连接（keep-alive）
_URL = None
_URL_LOCK = threading.Lock()

# 慢指标（外网探测 / 容器枚举 / 公网 IP）由后台采样线程刷新，
# 绝不能留在主轮询链路上：一次超时就可能把按键/开控制台命令拖住数秒。
_LAT = {"ts": 0.0, "out": {}}
_CTS = {"ts": 0.0, "out": {}}
_PUBIP = {"ip": "", "ts": 0.0}
_SLOW_LOCK = threading.Lock()


def log(m): print(f"[agent] {time.strftime('%H:%M:%S')} {m}", flush=True)

def _url():
    global _URL
    if _URL is None:
        with _URL_LOCK:
            if _URL is None:
                _URL = urlparse(API)
    return _URL

def _drop():
    c = getattr(_TLS, "c", None)
    if c is not None:
        _TLS.c = None
        try: c.close()
        except Exception: pass

def _conn(timeout):
    c = getattr(_TLS, "c", None)
    if c is not None:
        if getattr(c, "sock", None) is not None:
            try: c.sock.settimeout(timeout)
            except Exception: pass
        return c
    u = _url()
    host = u.hostname
    port = u.port or (443 if u.scheme == "https" else 80)
    if u.scheme == "https":
        c = _http_client.HTTPSConnection(host, port, timeout=timeout,
                                         context=ssl.create_default_context())
    else:
        c = _http_client.HTTPConnection(host, port, timeout=timeout)
    _TLS.c = c
    return c

def http(path, data=None, timeout=10):
    """走常驻连接（keep-alive）：省掉每次请求的 TCP+TLS 握手（跨境 ≈2-3 个 RTT）。
    连接被服务端回收/断开时自动重连一次，行为与旧的 urlopen 等价。"""
    body = json.dumps(data).encode() if data is not None else None
    method = "POST" if data is not None else "GET"
    prefix = _url().path.rstrip("/")
    hdrs = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json",
            "Accept": "application/json", "Connection": "keep-alive"}
    last = None
    for attempt in range(2):
        c = _conn(timeout)
        try:
            c.request(method, prefix + path, body=body, headers=hdrs)
            r = c.getresponse()
            raw = r.read()                       # 必须读完，否则连接不可复用
            if r.status >= 400:
                raise RuntimeError(f"http {r.status}")
            return json.loads(raw.decode() or "{}")
        except Exception as e:
            last = e
            _drop()
            if attempt == 0:
                time.sleep(0.05)
    raise last

def run(script, timeout=120):
    p = subprocess.run(["bash", "-c", script], capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)[-200000:]

# ---------- 指标采集 ----------
def host_metrics():
    cpu_pct = 0.0
    line = ""
    for ln in open("/proc/stat"):
        if ln.startswith("cpu "):
            line = ln.split()[1:9]; break
    if line:
        a = [int(x) for x in line]
        old = PREV.get("cpu_line")
        PREV["cpu_line"] = a
        if old:
            da, db_ = sum(old), sum(a)
            ia, ib = old[3] + old[4], a[3] + a[4]
            if db_ > da: cpu_pct = round(max((1-(ib-ia)/(db_-da))*100, 0), 1)
    t = a_kb = 0
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemTotal"): t = int(ln.split()[1])
        elif ln.startswith("MemAvailable"): a_kb = int(ln.split()[1]); break
    rx = tx = 0
    for i, ln in enumerate(open("/proc/net/dev")):
        if i < 2: continue
        name, dat = ln.split(":")
        if name.strip() != "lo":
            f = dat.split(); rx += int(f[0]); tx += int(f[8])
    rxp = PREV.get("rx"); txp = PREV.get("tx"); pt = PREV.get("net_t", time.time())
    now = time.time()
    rx_k = tx_k = 0.0
    if rxp is not None and now > pt:
        rx_k = round(max(rx-rxp,0)*8/1000/(now-pt),1); tx_k = round(max(tx-txp,0)*8/1000/(now-pt),1)
    PREV.update(rx=rx, tx=tx, net_t=now)
    du = os.statvfs("/")
    disk_t = du.f_blocks*du.f_frsize/1073741824
    disk_u = (du.f_blocks-du.f_bfree)*du.f_frsize/1073741824
    up = 0
    for ln in open("/proc/uptime"):
        up = int(float(ln.split()[0])); break
    try:
        l1, l5, l15 = os.getloadavg()
        load = [round(l1,2), round(l5,2), round(l15,2)]
    except Exception:
        load = [0,0,0]
    return {"load": load, "cpu_pct": cpu_pct, "mem_total_mb": round(t/1024),
            "mem_used_mb": round(max(t-a_kb,0)/1024),
            "disk_total_gb": round(disk_t,1), "disk_used_gb": round(disk_u,1),
            "rx_kbps": rx_k, "tx_kbps": tx_k, "uptime_s": up}

def containers():
    """一次 bash 调用拿全部容器状态（原来每个容器 4 次 subprocess，容器一多轮询就被拖住）"""
    out = {}
    try:
        script = r"""
for n in $(lxc-ls -1 2>/dev/null); do
  s=$(lxc-info -sH -n "$n" 2>/dev/null | tr -d ' \r')
  p=$(lxc-info -pH -n "$n" 2>/dev/null | tr -d ' \r')
  i=$(lxc-info -iH -n "$n" 2>/dev/null | tr -d ' \r' | head -1)
  printf '%s|%s|%s|%s\n' "$n" "$s" "$p" "$i"
done"""
        rc, so = run(script, 20)
        if rc != 0: return out
        prev = PREV["ct_cpu"]; newprev = {}
        now = time.time()
        dt = max(now - PREV.get("ct_t", now), 0.5)
        for ln in so.splitlines():
            parts = ln.split("|")
            if len(parts) != 4: continue
            n, st, pid, ip = parts
            st = st.lower() or "stopped"
            up = 0
            if pid.isdigit():
                try:
                    with open(f"/proc/{pid}/stat") as f:
                        fields = f.read().rsplit(") ", 1)[-1].split()
                    btime = None
                    for l2 in open("/proc/stat"):
                        if l2.startswith("btime"): btime = int(l2.split()[1]); break
                    clk = os.sysconf("SC_CLK_TCK") or 100
                    stime_ticks = int(fields[19])
                    now_u = time.time()
                    boot_u = now_u - float(open("/proc/uptime").read().split()[0])
                    up = max(int(now_u - (boot_u + stime_ticks / clk)), 0)
                except Exception:
                    pass
            mu = uu = 0
            d = f"/sys/fs/cgroup/lxc.payload.{n}"
            try: mu = int(open(d+"/memory.current").read())
            except Exception: pass
            try:
                for l3 in open(d+"/cpu.stat"):
                    if l3.startswith("usage_usec"): uu = int(l3.split()[1]); break
            except Exception: pass
            cpu_pct = 0.0
            if st == "running" and n in prev and prev[n] <= uu:
                cpu_pct = min((uu - prev[n]) / 1e6 / dt * 100, 400.0)
            newprev[n] = uu
            out[n] = {"state": st, "uptime_s": up if st == "running" else 0,
                      "mem_used_mb": round(mu/1048576, 1) if st == "running" else 0,
                      "cpu_pct": round(cpu_pct, 1), "ip": ip}
        PREV["ct_cpu"] = newprev
        PREV["ct_t"] = now
    except Exception as e:
        log("containers err: "+str(e))
    return out

def sysinfo():
    """系统静态信息 + 公网 IP（外网请求可能超时，只允许在后台线程里跑）"""
    rc, o = run(". /etc/os-release 2>/dev/null; printf '%s|%s' \"${PRETTY_NAME:-Linux}\" \"$(uname -r)\"")
    osname, _, kern = o.partition("|")
    pub = _PUBIP.get("ip", "")
    if time.time() - _PUBIP.get("ts", 0.0) > 300:
        _PUBIP["ts"] = time.time()
        try:
            req = urllib.request.Request("https://api.ipify.org")
            with urllib.request.urlopen(req, timeout=5) as r:
                pub = r.read().decode().strip()
            _PUBIP["ip"] = pub
        except Exception:
            pass
    return {"os": osname, "kernel": kern, "cores": os.cpu_count(),
            "hostname": socket.gethostname(), "public_ip": pub or _PUBIP.get("ip", "")}


def _slow_loop():
    """慢指标（公网探测类）后台刷新：主轮询线程永远只读缓存，
    这样外网被墙/超时也不会把终端命令的下发拖住几秒"""
    global _last_full
    while True:
        try:
            _cache_report["sys"] = sysinfo()
            _last_full = time.time()
        except Exception as e:
            log("sysinfo err: %s" % e)
        try:
            out = {}
            for name, h, p in (("Cloudflare", "1.1.1.1", 443), ("Google", "8.8.8.8", 53),
                               ("AliDNS", "223.5.5.5", 53)):
                try:
                    t0 = time.time()
                    c = socket.create_connection((h, p), timeout=2)
                    c.close()
                    out[name] = round((time.time() - t0) * 1000)
                except Exception:
                    out[name] = None
            _LAT["out"] = out
            _LAT["ts"] = time.time()
        except Exception as e:
            log("lat err: %s" % e)
        time.sleep(30)


def latencies():
    """读后台缓存的 TCP 握手延迟(毫秒)；首轮未就绪时为空，主循环不等待"""
    return _LAT["out"]


def full_report():
    rep = {"type": "report",
           "sys": _cache_report.get("sys") or {"os": "", "kernel": "", "cores": os.cpu_count(),
                                               "hostname": socket.gethostname(), "public_ip": ""},
           "host": host_metrics(), "cts": containers(), "latency": latencies()}
    return rep

_running: dict = {}

# ────────────── PTY 终端会话（浏览器 ⇄ 面板 ⇄ 本机） ──────────────
PTY: dict = {}          # sid -> {"m":master_fd,"p":Popen,"buf":bytearray,"seq":int,"eof":bool}


def _pty_open(cmd, sid, cols=120, rows=32):
    import fcntl, pty as _pty, signal, struct, termios
    try:
        mfd, sfd = _pty.openpty()
        p = subprocess.Popen(["bash", "-lc", cmd], stdin=sfd, stdout=sfd,
                             stderr=sfd, preexec_fn=os.setsid, close_fds=True)
        os.close(sfd)
        try:
            fcntl.ioctl(mfd, termios.TIOCSWINSZ,
                        struct.pack("HHHH", int(rows), int(cols), 0, 0))
        except Exception:
            pass
        PTY[sid] = {"m": mfd, "p": p, "buf": bytearray(), "seq": 0, "eof": False,
                    "ev": threading.Event(), "lk": threading.Lock()}
        threading.Thread(target=_pty_read, args=(sid,), daemon=True).start()
        threading.Thread(target=_pty_flush, args=(sid,), daemon=True).start()
        log(f"pty open {sid}: {cmd[:60]}")
    except Exception as e:
        log(f"pty open fail {sid}: {e}")
        try:
            http("/api/agent/pty_out",
                 {"sid": sid, "seq": 0,
                  "data": base64.b64encode(f"\r\n[agent] PTY 创建失败: {e}\r\n".encode()).decode(),
                  "closed": True}, timeout=10)
        except Exception:
            pass


def _pty_read(sid):
    s = PTY.get(sid)
    if not s:
        return
    while sid in PTY:
        try:
            data = os.read(s["m"], 65536)
        except OSError:
            break
        if not data:
            break
        with s["lk"]:
            s["buf"] += data
        s["ev"].set()                # 事件驱动：一有输出就唤醒发送线程
    try:
        s["p"].wait(timeout=5)
    except Exception:
        pass
    s["eof"] = True
    s["ev"].set()


def _pty_flush(sid):
    """事件驱动 + 8ms 合并窗口：单键回显几乎零等待，海量输出仍会聚成大块。
    （原来是固定 sleep(0.12) 轮询，白白给每一次回显再加 120ms。）"""
    s = PTY.get(sid)
    if not s:
        return
    while sid in PTY:
        if not s["ev"].wait(1.0):
            if s.get("eof"):
                break
            continue
        s["ev"].clear()
        time.sleep(0.008)                       # 合并窗口：同一次回显的残余字节
        with s["lk"]:
            data = bytes(s["buf"])
            s["buf"].clear()
        if data:
            payload = {"sid": sid, "seq": s["seq"],
                       "data": base64.b64encode(data).decode(), "closed": False}
            s["seq"] += 1
            ok = False
            for _ in range(2):                      # 失败重试一次
                try:
                    http("/api/agent/pty_out", payload, timeout=15); ok = True; break
                except Exception:
                    time.sleep(0.5)
            if not ok:
                log(f"pty out dropped {sid}#{payload['seq']}")
        if s.get("eof") and not s["buf"]:
            break
    try:
        http("/api/agent/pty_out", {"sid": sid, "seq": 0, "data": "", "closed": True},
             timeout=10)
    except Exception:
        pass
    _pty_kill(sid)


def _pty_kill(sid):
    import signal
    s = PTY.pop(sid, None)
    if not s:
        return
    try:
        s["ev"].set()                     # 唤醒可能阻塞在 wait() 上的发送线程，避免线程泄漏
    except Exception:
        pass
    try:
        os.killpg(os.getpgid(s["p"].pid), signal.SIGKILL)
    except Exception:
        pass
    try:
        os.close(s["m"])
    except Exception:
        pass


def _pty_handle(cmd):
    op = cmd.get("op"); sid = str(cmd.get("sid") or "")
    if not sid:
        return
    if op == "pty_open":
        if sid not in PTY:
            _pty_open(cmd.get("cmd") or "bash -li", sid,
                      cmd.get("cols") or 120, cmd.get("rows") or 32)
    elif op == "pty_in":
        s = PTY.get(sid)
        if s:
            try:
                data = base64.b64decode(cmd.get("data") or "")
                if data:
                    os.write(s["m"], data)
            except OSError:
                pass
    elif op == "pty_win":
        s = PTY.get(sid)
        if s:
            try:
                import fcntl, signal, struct, termios
                fcntl.ioctl(s["m"], termios.TIOCSWINSZ, struct.pack(
                    "HHHH", int(cmd.get("rows") or 32), int(cmd.get("cols") or 120), 0, 0))
                os.kill(s["p"].pid, signal.SIGWINCH)
            except Exception:
                pass
    elif op == "pty_close":
        _pty_kill(sid)


def _do_exec(cmd):
    cid = cmd.get("id","?")
    script = cmd.get("script","")
    if cmd.get("b64"):
        script = base64.b64decode(script).decode(errors="replace")
    try:
        rc, out = run(script, int(cmd.get("timeout") or 120))
    except subprocess.TimeoutExpired:
        rc, out = 124, "timeout"
    except Exception as e:
        rc, out = 1, str(e)
    try:
        http("/api/agent/result",
             {"id":cid,"rc":rc,"out":base64.b64encode(out.encode()).decode()},
             timeout=20)
        log(f"exec done {cid} rc={rc}")
    except Exception as e:
        log(f"result upload failed {cid}: {e}; will retry once")
        time.sleep(2)
        try:
            http("/api/agent/result",
                 {"id":cid,"rc":rc,"out":base64.b64encode(out.encode()).decode()}, timeout=20)
        except Exception as e2:
            log(f"result dropped {cid}: {e2}")
    finally:
        _running.pop(cid, None)


def main():
    global API, TOKEN
    for i, a in enumerate(sys.argv):
        if a == "--api" and i+1 < len(sys.argv): API = sys.argv[i+1]
        if a == "--token" and i+1 < len(sys.argv): TOKEN = sys.argv[i+1]
    # conf 与脚本同目录优先（支持非 root / 只读 /opt 的容器环境），旧路径兜底
    _here = os.path.dirname(os.path.abspath(__file__))
    conf_paths = [os.path.join(_here, "agent.conf"), CONF]
    if not API or not TOKEN:
        for _cp in conf_paths:
            try:
                conf = json.load(open(_cp)); API = conf["api"]; TOKEN = conf["token"]; break
            except Exception:
                continue
    if not API or not TOKEN:
        print("usage: agent.py --api https://panel --token TOKEN"); sys.exit(1)
    saved = "memory-only"
    for _cp in conf_paths:
        try:
            os.makedirs(os.path.dirname(_cp), exist_ok=True)
            json.dump({"api":API,"token":TOKEN}, open(_cp,"w"))
            os.chmod(_cp, 0o600)
            saved = _cp
            break
        except Exception:
            continue
    log(f"started {AGENT_VER} (conf={saved}), panel={API}")
    # 慢指标(公网IP/外网延迟探测)放后台线程刷，主轮询循环只读缓存：
    # 否则一次被墙的外网探测就能把终端命令的下发拖住好几秒
    try:
        _cache_report["sys"] = sysinfo()
    except Exception:
        pass
    threading.Thread(target=_slow_loop, daemon=True).start()
    fail = 0
    _last_rep: dict = {}
    while True:
        hold = 0.0
        try:
            fast = bool(PTY)                       # 有终端会话时加速轮询(输入低延迟)
            if fast and _last_rep:
                rep = dict(_last_rep); rep["type"] = "poll"
            else:
                rep = full_report(); _last_rep = dict(rep)
            rep["pending"] = list(_running.keys())
            rep["pty"] = list(PTY.keys())
            # 上报 + 取命令（一次往返）。新版面板在没命令时会把该请求挂起 hold 秒，
            # 于是按键/开控制台命令搭"已经挂着的这次请求"即时下发，不必等下一轮。
            data = http("/api/agent/poll", rep, timeout=12)
            fail = 0
            try:
                hold = float(data.get("hold") or 0)
            except Exception:
                hold = 0.0
            for cmd in (data.get("commands") or []):
                cid = cmd.get("id"); op = cmd.get("op")
                if op == "exec" and cid not in _running:
                    t = threading.Thread(target=_do_exec, args=(cmd,), daemon=True)
                    _running[cid] = t
                    t.start()
                elif op in ("pty_open", "pty_in", "pty_win", "pty_close"):
                    try:
                        _pty_handle(cmd)
                    except Exception as e:
                        log(f"pty cmd err: {e}")
        except Exception as e:
            fail += 1
            if fail % 10 == 1: log(f"offline: {e}; retrying...")
            time.sleep(min(2+fail, 10))
            continue
        # 面板挂了这次请求(新版) → 只需极短间隔继续下一轮；
        # 老版面板不 hold → 退回原来的 0.18s / 3s 节奏，避免打成洪水。
        if hold > 0:
            time.sleep(0.05 if PTY else 0.3)
        else:
            time.sleep(0.18 if PTY else 3)

if __name__ == "__main__":
    main()
'''

UNINSTALL_SH = r'''#!/bin/sh
# NexPanel Agent/探针 一键清理脚本
# 用法: curl -fsSL <面板地址>/api/agent/uninstall.sh | sh
pkill -f "/opt/lxcdeck-agent/agent.py" 2>/dev/null || true
sleep 1
if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now lxcdeck-agent >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/lxcdeck-agent.service /etc/systemd/system/multi-user.target.wants/lxcdeck-agent.service
  systemctl daemon-reload >/dev/null 2>&1 || true
elif command -v rc-service >/dev/null 2>&1; then
  rc-service lxcdeck-agent stop >/dev/null 2>&1 || true
  rc-update del lxcdeck-agent default >/dev/null 2>&1 || true
  rm -f /etc/init.d/lxcdeck-agent
fi
rm -rf /opt/lxcdeck-agent
command -v crontab >/dev/null 2>&1 && (crontab -l 2>/dev/null | grep -v "lxcdeck-agent/run-bg.sh" | crontab - >/dev/null 2>&1 || true)
if pgrep -f "/opt/lxcdeck-agent/agent.py" >/dev/null 2>&1; then
  echo "[WARN] 仍有残留进程，请手动执行: pkill -9 -f lxcdeck"
else
  echo "[OK] NexPanel Agent/探针 已从本机彻底清除（服务已停止并删除）"
fi
'''

INSTALL_SH = r'''#!/bin/sh
# NexPanel Agent 一键安装脚本（支持 Debian/Ubuntu/CentOS/Rocky/Alpine）
set -e
API="__API__"; TOKEN="__TOKEN__"
while [ "$#" -gt 0 ]; do
  case $1 in --api) API="$2"; shift;; --token) TOKEN="$2"; shift;; *) echo unknown $1; exit 1;; esac
  shift
done
[ -n "$API" ] && [ -n "$TOKEN" ] || { echo "缺少 --api/--token"; exit 1; }

# 安装依赖：bash + curl + wget + python3 + ca-certificates（按包管理器区分）
if ! command -v bash >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1 \
   || ! command -v wget >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  if command -v apk >/dev/null 2>&1; then
    apk add --no-cache bash curl wget python3 ca-certificates
  elif command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq bash curl wget python3 ca-certificates
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y bash curl wget python3 ca-certificates
  elif command -v yum >/dev/null 2>&1; then
    yum install -y bash curl wget python3 ca-certificates
  else
    echo "unsupported package manager"; exit 9
  fi
fi

mkdir -p /opt/lxcdeck-agent
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$API/api/agent/agent.py?token=$TOKEN" -o /opt/lxcdeck-agent/agent.py
else
  wget -qO /opt/lxcdeck-agent/agent.py "$API/api/agent/agent.py?token=$TOKEN"
fi
cat > /opt/lxcdeck-agent/agent.conf <<EOF2
{"api":"$API","token":"$TOKEN"}
EOF2
chmod 600 /opt/lxcdeck-agent/agent.conf

SVC_MODE=""
if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
  # systemd 正在运行（判断依据：PID1 为 systemd，/run/systemd/system 存在；
  # 仅凭 systemctl 命令存在会误判无 init 的容器环境）
  cat > /etc/systemd/system/lxcdeck-agent.service <<EOF2
[Unit]
Description=NexPanel Agent
After=network.target
[Service]
ExecStart=/usr/bin/python3 /opt/lxcdeck-agent/agent.py --api $API --token $TOKEN
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF2
  if systemctl daemon-reload >/dev/null 2>&1 \
     && systemctl enable --now lxcdeck-agent >/dev/null 2>&1; then
    SVC_MODE="systemd"
  else
    echo "[WARN] systemd 服务注册失败，回退为托管后台进程"
  fi
elif command -v rc-service >/dev/null 2>&1 && command -v openrc-run >/dev/null 2>&1; then
  # Alpine / OpenRC
  cat > /opt/lxcdeck-agent/run.sh <<EOF2
#!/bin/sh
exec /usr/bin/python3 /opt/lxcdeck-agent/agent.py --api $API --token $TOKEN
EOF2
  chmod +x /opt/lxcdeck-agent/run.sh
  cat > /etc/init.d/lxcdeck-agent <<EOF2
#!/sbin/openrc-run
name="lxcdeck-agent"
command="/bin/sh"
command_args="/opt/lxcdeck-agent/run.sh"
command_background=true
pidfile="/run/lxcdeck-agent.pid"
depend() {
  need net
}
EOF2
  chmod +x /etc/init.d/lxcdeck-agent
  rc-update add lxcdeck-agent default >/dev/null 2>&1 || true
  if rc-service lxcdeck-agent start >/dev/null 2>&1 \
     && rc-service lxcdeck-agent status >/dev/null 2>&1; then
    SVC_MODE="openrc"
  else
    echo "[WARN] OpenRC 服务启动失败，回退为托管后台进程"
  fi
fi
if [ -z "$SVC_MODE" ]; then
  # 无 init 系统（纯容器 / K8s Pod）：托管式后台拉起，日志与 pid 落盘，有 cron 则加 @reboot 自启
  cat > /opt/lxcdeck-agent/run-bg.sh <<EOF2
#!/bin/sh
pkill -f "/opt/lxcdeck-agent/agent.py" 2>/dev/null || true
sleep 1
if command -v setsid >/dev/null 2>&1; then
  setsid /usr/bin/python3 /opt/lxcdeck-agent/agent.py --api $API --token $TOKEN >>/opt/lxcdeck-agent/agent.log 2>&1 &
else
  nohup /usr/bin/python3 /opt/lxcdeck-agent/agent.py --api $API --token $TOKEN >>/opt/lxcdeck-agent/agent.log 2>&1 &
fi
echo \$! > /opt/lxcdeck-agent/agent.pid
EOF2
  chmod +x /opt/lxcdeck-agent/run-bg.sh
  /opt/lxcdeck-agent/run-bg.sh || true
  if command -v crontab >/dev/null 2>&1; then
    (crontab -l 2>/dev/null | grep -v "lxcdeck-agent/run-bg.sh"; \
     echo "@reboot /opt/lxcdeck-agent/run-bg.sh >/dev/null 2>&1") | crontab - >/dev/null 2>&1 || true
  fi
  SVC_MODE="background"
fi
sleep 2
ALIVE=0
if command -v pgrep >/dev/null 2>&1; then
  pgrep -f "/opt/lxcdeck-agent/agent.py" >/dev/null 2>&1 && ALIVE=1
elif [ -f /opt/lxcdeck-agent/agent.pid ]; then
  kill -0 "$(cat /opt/lxcdeck-agent/agent.pid)" 2>/dev/null && ALIVE=1
fi
if [ "$ALIVE" = "1" ]; then
  echo "[OK] NexPanel Agent 已上线 (mode=$SVC_MODE)"
else
  echo "[ERR] Agent 启动失败，请查看 /opt/lxcdeck-agent/agent.log"
  exit 1
fi
'''

UPGRADE_SH = r'''#!/bin/sh
# NexPanel Agent 自升级：备份 -> 从面板下载新版 -> 校验 -> 原子替换 -> 重启 -> 失败回滚
set -u
DIR=/opt/lxcdeck-agent
cd "$DIR" 2>/dev/null || { echo "[ERR] $DIR 不存在"; exit 1; }
[ -f agent.conf ] || { echo "[ERR] 缺少 agent.conf"; exit 1; }
API=$(sed -n 's/.*"api"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' agent.conf)
TOKEN=$(sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' agent.conf)
[ -n "$API" ] && [ -n "$TOKEN" ] || { echo "[ERR] agent.conf 解析失败"; exit 1; }

echo "==> [1/4] 备份当前版本"
cp -f agent.py agent.py.bak 2>/dev/null

echo "==> [2/4] 从面板下载新版"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL --max-time 60 "$API/api/agent/agent.py?token=$TOKEN" -o .new \
    || { echo "[ERR] 下载失败"; exit 1; }
else
  wget -qT 60 -O .new "$API/api/agent/agent.py?token=$TOKEN" \
    || { echo "[ERR] 下载失败"; exit 1; }
fi
[ -s .new ] || { echo "[ERR] 下载内容为空"; exit 1; }
head -1 .new | grep -q python || { echo "[ERR] 内容校验失败(非脚本)"; rm -f .new; exit 1; }
# 指纹：只认「本文件里确实定义了当前版本」。注意不能用 "started <版本>"——
# 运行时那行是 f"started {AGENT_VER}"，源码里没有这个字面量，历史上导致升级校验恒失败。
grep -qF 'AGENT_VER = "__AGENT_VER__"' .new || { echo "[ERR] 新版指纹缺失(面板代码未更新?)"; rm -f .new; exit 1; }
mv -f .new agent.py
date "+%Y-%m-%d %H:%M:%S" > version.txt

echo "==> [3/4] 重启服务加载新代码（setsid 独立会话，防止 stop 连带杀死本脚本）"
restart_svc() {
  if command -v systemctl >/dev/null 2>&1; then
    setsid sh -c 'systemctl restart lxcdeck-agent' >/dev/null 2>&1
  else
    setsid sh -c 'rc-service lxcdeck-agent restart' >/dev/null 2>&1
  fi
  sleep 3
  if command -v systemctl >/dev/null 2>&1; then
    systemctl is-active lxcdeck-agent 2>/dev/null
  else
    rc-service lxcdeck-agent status >/dev/null 2>&1 && echo active
  fi
}
if restart_svc; then
  echo "==> [4/4] 完成"
  echo "[OK] Agent 已升级 ($(cat version.txt)) __AGENT_VER__"
else
  echo "[WARN] 新版启动失败，自动回滚旧版本"
  mv -f agent.py.bak agent.py
  if restart_svc; then
    echo "[OK] 已回滚到旧版本，服务恢复"
  else
    echo "[ERR] 回滚后仍无法启动，请登录本机检查 systemctl status lxcdeck-agent"
  fi
fi
'''

# 版本指纹注入：UPGRADE_SH 里的 __AGENT_VER__ 占位符替换为当前 agent 版本
UPGRADE_SH = UPGRADE_SH.replace("__AGENT_VER__", AGENT_VER)
