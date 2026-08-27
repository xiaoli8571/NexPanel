"""Agent 体系：
* AGENT_PY   部署到目标 VPS 的常驻代理(纯标准库, HTTP 轮询, 无依赖)
* 面板侧     待下发命令队列 / 结果回收 / 心跳指标入缓存 / PTY 终端流转发
"""
import asyncio
import base64
import secrets
import subprocess
import time

# ────────────────────────── 面板侧状态 ──────────────────────────
_pending: dict[int, list] = {}       # node_id -> [cmd,...]
_results: dict[str, dict] = {}       # cmd_id -> {"rc":..,"out":..} / event style
_live: dict[int, float] = {}         # node_id -> last_seen ts (ws/http 均可)

# ── PTY 终端会话（浏览器 ⇄ 面板 ⇄ Agent 轮询流） ──
_pty_subs: dict[str, asyncio.Queue] = {}   # sid -> 输出队列 (str chunk / "__CLOSED__")
_pty_node: dict[str, int] = {}             # sid -> node_id (校验 pty_out 归属)


def open_pty(node_id: int, cmd: str, cols: int = 120, rows: int = 32) -> str:
    """在目标 Agent 上开启 PTY 会话，返回 sid"""
    sid = "p" + secrets.token_hex(8)
    _pty_subs[sid] = asyncio.Queue(maxsize=2000)
    _pty_node[sid] = node_id
    _pending.setdefault(node_id, []).append(
        {"id": "o" + secrets.token_hex(6), "op": "pty_open", "sid": sid,
         "cmd": cmd, "cols": max(40, min(cols, 500)), "rows": max(8, min(rows, 300))})
    return sid


def pty_input(sid: str, data: str):
    nid = _pty_node.get(sid)
    if nid is not None:
        _pending.setdefault(nid, []).append(
            {"id": "i" + secrets.token_hex(6), "op": "pty_in", "sid": sid,
             "data": base64.b64encode(data.encode("utf-8", errors="replace")).decode()})


def pty_resize(sid: str, cols: int, rows: int):
    nid = _pty_node.get(sid)
    if nid is not None:
        _pending.setdefault(nid, []).append(
            {"id": "w" + secrets.token_hex(6), "op": "pty_win", "sid": sid,
             "cols": max(40, min(cols, 500)), "rows": max(8, min(rows, 300))})


def close_pty(sid: str):
    """通知 Agent 关闭 PTY 并清理面板侧状态"""
    nid = _pty_node.pop(sid, None)
    q = _pty_subs.pop(sid, None)
    if nid is not None:
        _pending.setdefault(nid, []).append(
            {"id": "x" + secrets.token_hex(6), "op": "pty_close", "sid": sid})


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
    return cid


def wait_result(cmd_id: str, timeout: float = 300) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cmd_id in _results:
            return _results.pop(cmd_id)
        time.sleep(0.3)
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
    _results[cmd_id] = {"rc": rc, "out": out}


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
import base64, json, os, platform, socket, subprocess, sys, threading, time
import urllib.request

API, TOKEN = "", ""
CONF = "/opt/lxcdeck-agent/agent.conf"
PREV = {"cpu_line": None, "rx": None, "tx": None, "ct_cpu": {}}
_last_full = 0.0
_cache_report = {}

def log(m): print(f"[agent] {time.strftime('%H:%M:%S')} {m}", flush=True)

def http(path, data=None, timeout=10):
    req = urllib.request.Request(API.rstrip("/") + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": "Bearer " + TOKEN,
                 "Content-Type": "application/json"},
        method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

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
    out = {}
    try:
        rc, names = run("lxc-ls -1", 15)
        if rc != 0: return out
        prev = PREV["ct_cpu"]
        newprev = {}
        for n in names.split():
            st = "stopped"
            r2, so = run(f"lxc-info -sH -n {n} 2>/dev/null", 10)
            if r2 == 0 and so.strip(): st = so.strip().lower()
            pid = ""
            r2, po = run(f"lxc-info -pH -n {n} 2>/dev/null", 10)
            if r2 == 0: pid = po.strip()
            up = 0; ip = ""
            if pid:
                r2, uo = run(f"ps -o etimes= -p {pid} 2>/dev/null", 10)
                if uo.strip().isdigit(): up = int(uo.strip())
                r2, io = run(f"lxc-info -iH -n {n} 2>/dev/null", 10)
                ip = io.strip().splitlines()[0] if io.strip() else ""
            mu = uu = 0
            d = f"/sys/fs/cgroup/lxc.payload.{n}"
            try: mu = int(open(d+"/memory.current").read())
            except Exception: pass
            try:
                for ln in open(d+"/cpu.stat"):
                    if ln.startswith("usage_usec"): uu = int(ln.split()[1]); break
            except Exception: pass
            cpu_pct = 0.0
            if st == "running" and n in prev:
                dt = PREV.get("ct_dt", 3)
                cpu_pct = min((uu-prev[n])/1e6/dt*100, 400.0)
            newprev[n] = uu
            out[n] = {"state": st, "uptime_s": up if st=="running" else 0,
                      "mem_used_mb": round(mu/1048576,1) if st=="running" else 0,
                      "cpu_pct": round(cpu_pct,1), "ip": ip}
        PREV["ct_cpu"] = newprev
        PREV["ct_dt"] = 3.0
    except Exception as e:
        log("containers err: "+str(e))
    return out

def full_report():
    global _last_full, _cache_report
    now = time.time()
    if now - _last_full > 30 or not _cache_report:
        rc, o = run(". /etc/os-release 2>/dev/null; printf '%s|%s' \"${PRETTY_NAME:-Linux}\" \"$(uname -r)\"")
        osname, _, kern = o.partition("|")
        pub = ""
        try:
            r = urllib.request.urlopen(urllib.Request if False else urllib.request.Request(
                "https://api.ipify.org"), timeout=5)
            pub = r.read().decode().strip()
        except Exception:
            pass
        _cache_report["sys"] = {"os": osname, "kernel": kern,
                                "cores": os.cpu_count(),
                                "hostname": socket.gethostname(),
                                "public_ip": pub or ""}
        _last_full = now
    rep = {"type":"report","sys":_cache_report["sys"],
           "host":host_metrics(),"cts":containers(),
           "latency":latencies()}
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
        PTY[sid] = {"m": mfd, "p": p, "buf": bytearray(), "seq": 0, "eof": False}
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
        s["buf"] += data
    try:
        s["p"].wait(timeout=5)
    except Exception:
        pass
    s["eof"] = True


def _pty_flush(sid):
    s = PTY.get(sid)
    if not s:
        return
    while sid in PTY:
        time.sleep(0.12)
        if s["buf"]:
            data = bytes(s["buf"]); s["buf"].clear()
            payload = {"sid": sid, "seq": s["seq"],
                       "data": base64.b64encode(data).decode(), "closed": False}
            s["seq"] += 1
            ok = False
            for _ in range(2):                      # 失败重试一次
                try:
                    http("/api/agent/pty_out", payload, timeout=15); ok = True; break
                except Exception:
                    time.sleep(1)
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


def latencies():
    """TCP 握手延迟探测(毫秒)：常用公共节点"""
    import socket as s
    out = {}
    for name, h, p in (("Cloudflare","1.1.1.1",443), ("Google","8.8.8.8",53),
                       ("AliDNS","223.5.5.5",53)):
        try:
            t0 = time.time()
            c = s.create_connection((h,p), timeout=3); c.close()
            out[name] = round((time.time()-t0)*1000)
        except Exception:
            out[name] = None
    return out


def main():
    global API, TOKEN
    for i, a in enumerate(sys.argv):
        if a == "--api" and i+1 < len(sys.argv): API = sys.argv[i+1]
        if a == "--token" and i+1 < len(sys.argv): TOKEN = sys.argv[i+1]
    if not API or not TOKEN:
        try:
            conf = json.load(open(CONF)); API = conf["api"]; TOKEN = conf["token"]
        except Exception:
            print("usage: agent.py --api https://panel --token TOKEN"); sys.exit(1)
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    json.dump({"api":API,"token":TOKEN}, open(CONF,"w"))
    os.chmod(CONF, 0o600)
    log(f"started v20260827 (poll=0.18s when pty), panel={API}")
    fail = 0
    _last_rep: dict = {}
    while True:
        try:
            fast = bool(PTY)                       # 有终端会话时加速轮询(输入低延迟)
            if fast and _last_rep:
                rep = dict(_last_rep); rep["type"] = "poll"
            else:
                rep = full_report(); _last_rep = dict(rep)
            rep["pending"] = list(_running.keys())
            rep["pty"] = list(PTY.keys())
            # 上报 + 取命令（一次往返）
            data = http("/api/agent/poll", rep, timeout=12)
            fail = 0
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

if command -v systemctl >/dev/null 2>&1; then
  # systemd 发行版（Debian/Ubuntu/CentOS/Rocky 等）
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
  systemctl daemon-reload
  systemctl enable --now lxcdeck-agent
  sleep 2
  systemctl is-active lxcdeck-agent && echo "[OK] NexPanel Agent 已上线"
elif command -v rc-service >/dev/null 2>&1; then
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
  rc-service lxcdeck-agent start
  sleep 2
  rc-service lxcdeck-agent status >/dev/null 2>&1 && echo "[OK] NexPanel Agent 已上线"
else
  echo "[WARN] 未检测到 systemd/OpenRC，请手动执行: nohup python3 /opt/lxcdeck-agent/agent.py --api $API --token $TOKEN &"
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
grep -q "started v20260827" .new || { echo "[ERR] 新版指纹缺失(面板代码未更新?)"; rm -f .new; exit 1; }
mv -f .new agent.py
date "+%Y-%m-%d %H:%M:%S" > version.txt

echo "==> [3/4] 重启服务加载新代码"
restart_svc() {
  if command -v systemctl >/dev/null 2>&1; then
    systemctl restart lxcdeck-agent; sleep 2; systemctl is-active lxcdeck-agent 2>/dev/null
  else
    rc-service lxcdeck-agent restart; sleep 2; rc-service lxcdeck-agent status >/dev/null 2>&1
  fi
}
if restart_svc; then
  echo "==> [4/4] 完成"
  echo "[OK] Agent 已升级 ($(cat version.txt)) v20260827"
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
