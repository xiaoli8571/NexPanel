"""Agent 体系：
* AGENT_PY   部署到目标 VPS 的常驻代理(纯标准库, HTTP 轮询, 无依赖)
* 面板侧     待下发命令队列 / 结果回收 / 心跳指标入缓存
"""
import base64
import secrets
import subprocess
import time

# ────────────────────────── 面板侧状态 ──────────────────────────
_pending: dict[int, list] = {}       # node_id -> [cmd,...]
_results: dict[str, dict] = {}       # cmd_id -> {"rc":..,"out":..} / event style
_live: dict[int, float] = {}         # node_id -> last_seen ts (ws/http 均可)


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
"""LXC Deck Agent — 反向接入面板，零依赖(HTTP 轮询)。安装即接管。"""
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
    log(f"started, panel={API}")
    fail = 0
    while True:
        try:
            rep = full_report()
            rep["pending"] = list(_running.keys())
            # 上报 + 取命令（一次往返）
            data = http("/api/agent/poll", rep, timeout=12)
            fail = 0
            for cmd in (data.get("commands") or []):
                cid = cmd.get("id"); op = cmd.get("op")
                if op == "exec" and cid not in _running:
                    t = threading.Thread(target=_do_exec, args=(cmd,), daemon=True)
                    _running[cid] = t
                    t.start()
        except Exception as e:
            fail += 1
            if fail % 10 == 1: log(f"offline: {e}; retrying...")
            time.sleep(min(2+fail, 10))
            continue
        time.sleep(3)

if __name__ == "__main__":
    main()
'''

INSTALL_SH = r'''#!/bin/sh
# LXC Deck Agent 一键安装脚本
set -e
API="__API__"; TOKEN="__TOKEN__"
while [ "$#" -gt 0 ]; do
  case $1 in --api) API="$2"; shift;; --token) TOKEN="$2"; shift;; *) echo unknown $1; exit 1;; esac
  shift
done
[ -n "$API" ] && [ -n "$TOKEN" ] || { echo "缺少 --api/--token"; exit 1; }
command -v curl >/dev/null || { apt-get update -qq; apt-get install -y -qq curl; }
command -v python3 >/dev/null || apt-get install -y -qq python3
mkdir -p /opt/lxcdeck-agent
curl -fsSL "$API/api/agent/agent.py?token=$TOKEN" -o /opt/lxcdeck-agent/agent.py
cat > /opt/lxcdeck-agent/agent.conf <<EOF2
{"api":"$API","token":"$TOKEN"}
EOF2
chmod 600 /opt/lxcdeck-agent/agent.conf
cat > /etc/systemd/system/lxcdeck-agent.service <<EOF2
[Unit]
Description=LXC Deck Agent
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
systemctl is-active lxcdeck-agent && echo "[OK] LXC Deck Agent 已上线"
'''
