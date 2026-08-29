"""节点级住宅出口（复刻 X-UI-Server / Free-Residential-IP-Proxy-Controller 方案）

免费住宅 IP 链路（已在 oc2 宿主原型验证）：
  VPN Gate（vpngate.net/api/iphone，志愿者家庭宽带 OpenVPN 中继）→ 按国家筛选优选
  → openvpn 单隧道（--route-nopull，不劫持系统路由）→ SOCKS5:7920
  （出站 socket SO_BINDTODEVICE=resi_tun，流量只走隧道）
面板只做「选国家」：部署 agent（systemd nexpanel-resi）+ 写 country 文件 + 重启。

应用侧（egress.py）出站 = socks5 → 宿主网桥 IP:7920（容器内）或 127.0.0.1:7920（宿主直装）。
"""
import json
import time

# 面板侧可选国家（VPN Gate 覆盖的常用国家）
COUNTRY_LIST = [
    ("JP", "日本"), ("US", "美国"), ("SG", "新加坡"), ("HK", "香港"),
    ("TW", "台湾"), ("KR", "韩国"), ("DE", "德国"), ("FR", "法国"),
    ("NL", "荷兰"), ("GB", "英国"), ("CA", "加拿大"), ("AU", "澳大利亚"),
    ("IT", "意大利"), ("ES", "西班牙"), ("SE", "瑞典"), ("CH", "瑞士"),
    ("RU", "俄罗斯"), ("IN", "印度"), ("BR", "巴西"), ("MX", "墨西哥"),
    ("TR", "土耳其"), ("PL", "波兰"), ("CZ", "捷克"), ("UA", "乌克兰"),
]

# ───────── 节点宿主守护 agent（单文件，无第三方依赖） ─────────
RESI_AGENT = r'''#!/usr/bin/env python3
"""NexPanel Residential Egress Agent — VPN Gate free residential IP (X-UI compatible)"""
import base64, csv, io, json, os, select, signal, socket, subprocess, sys, threading, time, urllib.request

BASE = "/etc/nexpanel-resi"
COUNTRY_F = BASE + "/country"
STATUS_F = BASE + "/status.json"
PORT = 7920
DEV = "resi_tun"
API = "https://www.vpngate.net/api/iphone/"

def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)

_state = {"state": "starting", "msg": "", "egress_ip": "", "isp": "", "hosting": None, "node": ""}
_cur_proc = {"p": None}

def write_status(country):
    st = {"country": country, "state": _state["state"], "egress_ip": _state["egress_ip"],
          "isp": _state["isp"], "hosting": _state["hosting"], "node": _state["node"],
          "bridge_ip": _bridge_ip(), "port": PORT, "msg": _state["msg"], "updated_at": int(time.time())}
    try:
        tmp = STATUS_F + ".tmp"
        with open(tmp, "w") as f: f.write(json.dumps(st))
        os.replace(tmp, STATUS_F)
    except Exception as e:
        log("write_status fail:", e)

def _bridge_ip():
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True).stdout
        default_if = subprocess.run("ip route | awk '/^default/{print $5; exit}'",
                                    shell=True, capture_output=True, text=True).stdout.strip()
        for line in out.splitlines():
            p = line.split()
            if len(p) < 4: continue
            ifname = p[1]
            if ifname in ("lo", default_if) or ifname.startswith(("eth", "ens", "enp", "venet", "tun", "resi")):
                continue
            if ifname.startswith(("lxcbr", "virbr", "br-", "nexbr", "br0", "lxdbr")):
                return p[3].split("/")[0]
    except Exception:
        pass
    return "10.0.3.1"

_cache = {"ts": 0.0, "by_c": {}}
def fetch_nodes(country, max_nodes=10):
    now = time.time()
    if now - _cache["ts"] > 900 or country not in _cache["by_c"]:
        req = urllib.request.Request(API, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=30).read().decode()
        lines = raw.splitlines()
        hdr_i = next(i for i, l in enumerate(lines) if l.startswith("#HostName"))
        keep = [lines[hdr_i].lstrip("#")] + [l for l in lines if l and not l.startswith("#")]
        rows = list(csv.DictReader(io.StringIO("\n".join(keep))))
        by_c = {}
        for r in rows:
            cs = (r.get("CountryShort") or "").upper()
            if cs and r.get("OpenVPN_ConfigData_Base64"):
                by_c.setdefault(cs, []).append(r)
        _cache["by_c"] = by_c; _cache["ts"] = now
    nodes = sorted(_cache["by_c"].get(country, []),
                   key=lambda r: (int(r.get("Ping") or 9999), -int(r.get("Score") or 0)))
    return nodes[:max_nodes]

def curl_via_tun(url, timeout=12):
    r = subprocess.run(["curl", "-s", "-m", str(timeout), "--interface", DEV, url],
                       capture_output=True, text=True)
    return r.stdout.strip()

def health_check(country):
    ip = curl_via_tun("https://api.ipify.org")
    if not ip or (ip.count(".") != 3 and ":" not in ip):
        return None
    geo = curl_via_tun("http://ip-api.com/json/?fields=countryCode,isp,hosting", 10)
    try:
        g = json.loads(geo)
    except Exception:
        return None
    if (g.get("countryCode") or "").upper() != country:
        return None
    return {"ip": ip, "isp": g.get("isp", ""), "hosting": bool(g.get("hosting"))}

def connect_once(row):
    ovpn = base64.b64decode(row["OpenVPN_ConfigData_Base64"]).decode(errors="ignore")
    cfg = BASE + "/try.ovpn"
    with open(cfg, "w") as f: f.write(ovpn)
    with open(BASE + "/auth.txt", "w") as f: f.write("vpn\nvpn\n")
    lf = open(BASE + "/ovpn.log", "w")
    proc = subprocess.Popen(
        ["openvpn", "--config", cfg, "--dev", DEV, "--dev-type", "tun", "--nobind",
         "--route-nopull", "--pull-filter", "ignore", "route-ipv6",
         "--pull-filter", "ignore", "ifconfig-ipv6", "--auth-user-pass", BASE + "/auth.txt",
         "--auth-nocache", "--connect-timeout", "5", "--connect-retry-max", "1", "--verb", "3",
         "--data-ciphers", "AES-128-CBC:AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305",
         "--data-ciphers-fallback", "AES-128-CBC"],
        stdout=lf, stderr=subprocess.STDOUT)
    return proc, lf

def kill_cur():
    p = _cur_proc.get("p")
    if p:
        try: p.terminate()
        except Exception: pass
        _cur_proc["p"] = None
    subprocess.run(["ip", "link", "del", DEV], capture_output=True)

# ── SOCKS5（SO_BINDTODEVICE 绑隧道，no-auth，原型已验证） ──
def _relay(a, b):
    try:
        while True:
            r, _, e = select.select([a, b], [], [a, b], 180)
            if e: return
            for s in r:
                d = s.recv(65536)
                if not d: return
                (b if s is a else a).sendall(d)
    finally:
        try: a.close()
        except Exception: pass
        try: b.close()
        except Exception: pass

def _socks_client(c):
    out = None
    try:
        c.settimeout(15)
        hdr = c.recv(2)
        if len(hdr) < 2: return
        if hdr[1] > 0: c.recv(hdr[1])          # discard methods
        c.sendall(b"\x05\x00")                  # no-auth
        rq = c.recv(4)
        atyp = rq[3]
        if atyp == 1: host = socket.inet_ntoa(c.recv(4))
        elif atyp == 3:
            hl = c.recv(1)[0]; host = c.recv(hl).decode()
        else:
            c.sendall(b"\x05\x08\x00\x01" + b"\x00" * 6); return
        port_t = int.from_bytes(c.recv(2), "big")
        try:
            addrs = socket.getaddrinfo(host, port_t, socket.AF_INET, socket.SOCK_STREAM) or \
                    socket.getaddrinfo(host, port_t, 0, socket.SOCK_STREAM)
        except OSError:
            c.sendall(b"\x05\x04\x00\x01" + b"\x00" * 6); return
        last = None
        for af, st, pr, cn, sa in addrs:        # v4 优先逐个试（隧道无 v6）
            out = socket.socket(af, st, pr); out.settimeout(20)
            out.setsockopt(socket.SOL_SOCKET, 25, DEV.encode())   # SO_BINDTODEVICE
            try:
                out.connect(sa); break
            except OSError as e:
                last = e
                try: out.close()
                except Exception: pass
                out = None
        if out is None:
            raise last or OSError("no route")
        c.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + (1080).to_bytes(2, "big"))
        c.settimeout(None)
        _relay(c, out)
    except Exception as e:
        log("socks5 client err:", repr(e))
        try: c.sendall(b"\x05\x01\x00\x01" + b"\x00" * 6)
        except Exception: pass
    finally:
        try: c.close()
        except Exception: pass

def serve_socks():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT)); srv.listen(64)
    log("socks5 :%d (bind %s) listening" % (PORT, DEV))
    while True:
        try:
            c, _ = srv.accept()
            threading.Thread(target=_socks_client, args=(c,), daemon=True).start()
        except Exception:
            time.sleep(1)

def main():
    signal.signal(signal.SIGTERM, lambda *_: (kill_cur(), sys.exit(0)))
    os.makedirs(BASE, exist_ok=True)
    threading.Thread(target=serve_socks, daemon=True).start()
    dead = set()
    while True:
        try:
            country = open(COUNTRY_F).read().strip().upper() or "JP"
        except Exception:
            country = "JP"
        _state.update(state="pending", msg="fetch node list", egress_ip="")
        write_status(country)
        try:
            nodes = fetch_nodes(country)
        except Exception as e:
            _state.update(msg="vpngate fetch fail: %s" % e); write_status(country)
            time.sleep(60); continue
        if not nodes:
            _state.update(msg="no node for %s" % country); write_status(country)
            time.sleep(60); continue
        for r in nodes:
            if r.get("IP") in dead: continue
            _state.update(state="pending", msg="connect " + r.get("HostName", "?"), node=r.get("HostName", ""))
            write_status(country)
            proc, lf = connect_once(r); _cur_proc["p"] = proc
            ready = False
            for _ in range(18):
                if proc.poll() is not None: break
                time.sleep(1)
                try:
                    if "Initialization Sequence Completed" in open(BASE + "/ovpn.log").read():
                        ready = True; break
                except Exception: pass
            if not ready:
                kill_cur(); dead.add(r.get("IP"))
                if len(dead) > 60: dead.clear()
                continue
            h = health_check(country)
            if not h:
                log("health fail:", r.get("HostName"))
                kill_cur(); dead.add(r.get("IP")); continue
            _state.update(state="ready", egress_ip=h["ip"], isp=h["isp"],
                          hosting=h["hosting"], node=r.get("HostName", ""), msg="ready")
            write_status(country)
            log("tunnel ready: %s (%s) via %s" % (h["ip"], h["isp"], r.get("HostName")))
            while True:   # 维持 + watchdog
                if proc.poll() is not None:
                    log("tunnel down, redial"); break
                time.sleep(5)
                try:
                    cc = open(COUNTRY_F).read().strip().upper() or "JP"
                    if cc != country:
                        log("country changed, redial"); break
                except Exception: pass
                if int(time.time()) % 60 < 5:
                    h2 = health_check(country)
                    if h2:
                        _state.update(egress_ip=h2["ip"], isp=h2["isp"], hosting=h2["hosting"])
                        write_status(country)
                    else:
                        log("recheck fail, redial"); kill_cur(); break
            kill_cur(); dead.add(r.get("IP")); break   # 断开/换国后回主循环
        time.sleep(3)

if __name__ == "__main__":
    main()
'''

# ───────── 节点宿主侧 shell 脚本（经 deploy._exec_on_node 下发） ─────────

DEPLOY_SH = '''set -e
mkdir -p /opt/nexpanel-resi /etc/nexpanel-resi
if ! command -v openvpn >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq >/dev/null 2>&1 || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openvpn >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y openvpn
  elif command -v apk >/dev/null 2>&1; then apk add --no-cache openvpn
  elif command -v dnf >/dev/null 2>&1; then dnf install -y -q openvpn
  elif command -v yum >/dev/null 2>&1; then yum install -y -q openvpn
  fi
fi
command -v openvpn >/dev/null 2>&1 || {{ echo NO_OPENVPN; exit 1; }}
command -v python3 >/dev/null 2>&1 || {{
  apt-get install -y -qq python3 >/dev/null 2>&1 || apk add --no-cache python3 >/dev/null 2>&1 || dnf install -y -q python3 >/dev/null 2>&1 || true
}}
command -v python3 >/dev/null 2>&1 || {{ echo NO_PYTHON3; exit 1; }}
command -v curl >/dev/null 2>&1 || {{
  apt-get install -y -qq curl >/dev/null 2>&1 || apk add --no-cache curl >/dev/null 2>&1 || dnf install -y -q curl >/dev/null 2>&1 || true
}}
echo {agent_b64} | base64 -d > /opt/nexpanel-resi/resi_agent.py
[ -f /etc/nexpanel-resi/country ] || echo JP > /etc/nexpanel-resi/country
cat > /etc/systemd/system/nexpanel-resi.service <<'EOF_UNIT'
[Unit]
Description=NexPanel Residential Egress (VPN Gate)
After=network-online.target

[Service]
ExecStart=/usr/bin/env python3 /opt/nexpanel-resi/resi_agent.py
Restart=always
RestartSec=5
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF_UNIT
systemctl daemon-reload
systemctl enable --now nexpanel-resi >/dev/null 2>&1 || systemctl restart nexpanel-resi
sleep 2
systemctl is-active nexpanel-resi
echo DEPLOY_DONE
'''

SET_COUNTRY_SH = '''mkdir -p /etc/nexpanel-resi
echo "{country}" > /etc/nexpanel-resi/country
systemctl restart nexpanel-resi 2>/dev/null || {{ echo NO_SERVICE; exit 1; }}
sleep 1
systemctl is-active nexpanel-resi
echo COUNTRY_SET_{country}
'''

STATUS_SH = '''echo "SERVICE:$(systemctl is-active nexpanel-resi 2>/dev/null || echo inactive)"
cat /etc/nexpanel-resi/status.json 2>/dev/null || echo "{{}}"
'''

UNINSTALL_SH = '''systemctl disable --now nexpanel-resi 2>/dev/null || true
pkill -f resi_agent.py 2>/dev/null || true
ip link del resi_tun 2>/dev/null || true
rm -rf /opt/nexpanel-resi /etc/nexpanel-resi /etc/systemd/system/nexpanel-resi.service
systemctl daemon-reload 2>/dev/null || true
echo UNINSTALL_DONE
'''

_status_cache = {}  # node_id -> (ts, status dict)


async def _run(node, script, timeout=600):
    from . import deploy as deploy_mod
    j = {"id": "resi-%s-%d" % (node["id"], int(time.time())), "log": [], "status": "", "result": None}
    rc, out = await deploy_mod._exec_on_node(node, script, j, timeout)
    if rc != 0:
        raise RuntimeError("节点脚本失败 rc=%s: %s" % (rc, out[-300:]))
    return out


def _agent_b64() -> str:
    import base64
    return base64.b64encode(RESI_AGENT.encode()).decode()


async def deploy_residential(node) -> str:
    """节点宿主安装依赖 + 落 agent + systemd 拉起（幂等，重复调用即更新）"""
    return await _run(node, DEPLOY_SH.format(agent_b64=_agent_b64()))


async def set_country(node, country: str) -> str:
    return await _run(node, SET_COUNTRY_SH.format(country=country), timeout=120)


async def get_status(node) -> dict:
    """查节点宿主住宅服务状态（30s 缓存）"""
    key = node.get("id") if isinstance(node, dict) else node
    ts, data = _status_cache.get(key, (0.0, None))
    if data is not None and time.time() - ts < 30:
        return data
    try:
        out = await _run(node, STATUS_SH, timeout=90)
        service = "unknown"
        status = {}
        for line in out.splitlines():
            if line.startswith("SERVICE:"):
                service = line.split(":", 1)[1].strip()
            elif line.strip().startswith("{"):
                try:
                    status = json.loads(line)
                except Exception:
                    pass
        data = {"service": service, **status}
    except Exception as e:
        data = {"service": "unknown", "state": "unknown", "msg": str(e)[:200]}
    _status_cache[key] = (time.time(), data)
    return data


async def cached_host_status(node_id, node):
    """deploy._sync_machine_singbox 用：只拿 bridge_ip（读缓存，miss 时才打节点）"""
    ts, data = _status_cache.get(node_id, (0.0, None))
    if data is not None and time.time() - ts < 30:
        return data
    return await get_status(node)


async def uninstall(node) -> str:
    _status_cache.pop(node.get("id", 0), None)
    return await _run(node, UNINSTALL_SH, timeout=120)

