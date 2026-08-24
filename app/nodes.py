"""远程节点操作层：SSH 连接、命令执行、LXC 探测/安装、指标采集"""
import io
import time

import paramiko

from . import crypto

# 每次采集输出的轻量脚本：容器状态 + cgroup 内存/CPU + 宿主 CPU/内存/磁盘/网卡
COLLECT_SH = r'''
PATH="$PATH:/usr/sbin:/usr/bin:/sbin:/bin"
if ! command -v lxc-start >/dev/null 2>&1; then
  echo "__NOLXC__"
else
for n in $(lxc-ls -1 2>/dev/null); do
  st=$(lxc-info -sH -n "$n" 2>/dev/null); st=${st:-stopped}
  pid=$(lxc-info -pH -n "$n" 2>/dev/null)
  up=0; [ -n "$pid" ] && up=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d " ")
  ip=$(lxc-info -iH -n "$n" 2>/dev/null | head -n1)
  d="/sys/fs/cgroup/lxc.payload.$n"
  mu=0; uu=0
  [ -r "$d/memory.current" ] && mu=$(cat "$d/memory.current" 2>/dev/null)
  [ -r "$d/cpu.stat" ] && uu=$(awk '/^usage_usec/{print $2}' "$d/cpu.stat" 2>/dev/null)
  printf "CT\t%s|%s|%s|%s|%s|%s\n" "$n" "$st" "${up:-0}" "${mu:-0}" "${uu:-0}" "$ip"
done
fi
grep "^cpu " /proc/stat | head -n1
awk 'NR>2 {split($1,a,":"); gsub(/ /,"",a[1]); if(a[1]!="lo" && a[1]!=""){rx+=$2; tx+=$10}} END{printf "NET %d %d\n", rx+0, tx+0}' /proc/net/dev
df -kP / | tail -n1 | awk '{printf "DISK %d %d\n", $2, $3}'
awk '/^MemTotal/{t=$2} /^MemAvailable/{a=$2} END{printf "MEM %d %d\n", t, a}' /proc/meminfo
(. /etc/os-release 2>/dev/null; printf "OSINFO %s|%s|%s|%s\n" "${PRETTY_NAME:-Linux}" "$(uname -r)" "$(nproc 2>/dev/null || echo 1)" "$(hostname)")
PUBIP=""
if command -v curl >/dev/null 2>&1; then PUBIP=$(curl -fsSL --max-time 3 https://api.ipify.org 2>/dev/null); fi
if [ -z "$PUBIP" ] && command -v wget >/dev/null 2>&1; then PUBIP=$(wget -qO- --timeout=3 https://api.ipify.org 2>/dev/null); fi
printf "PUBIP %s\n" "$PUBIP"
'''

INSTALL_SH = r'''
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq; apt-get install -y -qq lxc
elif command -v dnf >/dev/null 2>&1; then dnf install -y lxc lxc-templates
elif command -v yum >/dev/null 2>&1; then yum install -y lxc lxc-templates
elif command -v apk >/dev/null 2>&1; then apk add --no-cache lxc lxc-templates
else echo "unsupported package manager"; exit 9; fi
command -v lxc-start && lxc-start --version
'''

PROBE_SH = (
    '. /etc/os-release 2>/dev/null; '
    'printf "META|%s|%s|%s|%s\\n" "${PRETTY_NAME:-Linux}" "$(uname -r)" "$(nproc)" "$(hostname)"; '
    'awk \'/^MemTotal/{printf "MEMK|%d\\n", $2}\' /proc/meminfo; '
    'if command -v lxc-start >/dev/null 2>&1; then '
    '  printf "LXC|%s\\n" "$(lxc-start --version 2>/dev/null)"; '
    'else echo "LXC|none"; fi')


def _load_key(pem: str):
    for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        try:
            return cls.from_private_key(io.StringIO(pem))
        except Exception:
            continue
    raise ValueError("无法解析私钥（支持 RSA / Ed25519 / ECDSA）")


def connect(nrow) -> paramiko.SSHClient:
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    secret = crypto.dec(nrow["secret"]) if nrow["secret"] else ""
    kw = dict(hostname=nrow["host"], port=int(nrow["port"] or 22),
              username=nrow["username"], timeout=10, banner_timeout=15,
              auth_timeout=15, allow_agent=False, look_for_keys=False)
    if nrow["auth_type"] == "key":
        kw["pkey"] = _load_key(secret)
    else:
        kw["password"] = secret
    cli.connect(**kw)
    return cli


def run_cmd(nrow, cmd: str, timeout: int = 30, pty: bool = False,
            client: paramiko.SSHClient | None = None) -> tuple[int, str]:
    """执行命令并返回 (rc, 合并输出)。传入 client 则复用连接。"""
    own = client is None
    cli = client or connect(nrow)
    try:
        _, stdout, _ = cli.exec_command(cmd, timeout=timeout, get_pty=pty)
        out = stdout.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        return rc, out.strip()
    finally:
        if own:
            cli.close()


def test_node(nrow) -> dict:
    """连接测试：返回系统信息与 LXC 安装状态（不落库）"""
    cli = connect(nrow)
    try:
        rc, out = run_cmd(nrow, PROBE_SH, timeout=25, client=cli)
        if rc != 0 or "META|" not in out:
            raise RuntimeError(f"探测失败 rc={rc}")
        info = {"ok": True, "os": "", "kernel": "", "cores": 1, "hostname": "",
                "mem_gb": 0, "lxc_installed": False, "lxc_version": ""}
        for line in out.splitlines():
            p = line.split("|")
            if line.startswith("META|") and len(p) >= 5:
                info.update(os=p[1], kernel=p[2], hostname=p[4])
                try:
                    info["cores"] = int(p[3] or 1)
                except ValueError:
                    pass
            elif line.startswith("MEMK|"):
                info["mem_gb"] = round(int(p[1]) / 1048576, 1)
            elif line.startswith("LXC|"):
                info["lxc_installed"] = p[1] != "none"
                info["lxc_version"] = "" if p[1] == "none" else p[1]
        return info
    finally:
        cli.close()


def install_lxc(nrow) -> str:
    """在节点上安装 LXC（可能耗时数分钟），返回输出尾部"""
    rc, out = run_cmd(nrow, INSTALL_SH, timeout=900, pty=True)
    tail = "\n".join(out.splitlines()[-25:])
    rc2, ver = run_cmd(nrow,
        'command -v lxc-start >/dev/null 2>&1 && lxc-start --version || echo MISSING',
        timeout=20)
    if "MISSING" in ver:
        raise RuntimeError(f"安装后仍未检测到 LXC:\n{tail}")
    return f"LXC {ver.strip()} 安装成功\n\n{tail}"


def parse_collect(text: str, prev: dict, dt: float) -> dict:
    """解析采集输出 → 节点缓存条目（与上次采样做差得到 CPU%/网速）"""
    entry: dict = {"status": "online", "error": "", "updated": time.time(),
                   "host": None, "cts": {}}
    if "__NOLXC__" in text:
        entry["status"] = "nolxc"
        entry["error"] = "节点未安装 LXC（可在节点卡片一键安装）"

    ct_cpu_prev: dict = prev.setdefault("ct_cpu", {})
    ct_cpu_new: dict = {}
    host = {"os": "Linux", "kernel": "", "cores": 4, "hostname": "", "public_ip": ""}

    for raw in text.splitlines():
        if raw.startswith("CT\t"):
            try:
                name, st, up, mu, uu, ip = (raw.split("\t", 1)[1].split("|") + [""])[:6]
            except Exception:
                continue
            running = st.strip().lower() == "running"
            st = st.strip().lower()
            usage = int(uu or 0)
            cpu_pct = 0.0
            if running and name in ct_cpu_prev and dt > 0:
                cpu_pct = min((usage - ct_cpu_prev[name]) / 1e6 / dt * 100, 400.0)
            ct_cpu_new[name] = usage
            entry["cts"][name] = {"state": st, "uptime_s": int(up or 0),
                                  "mem_used_mb": round(int(mu or 0) / 1048576, 1),
                                  "cpu_pct": round(cpu_pct, 1), "ip": ip.strip()}
        elif raw.startswith("cpu "):
            old = prev.get("cpu_line")
            prev["cpu_line"] = raw
            if old:
                try:
                    a = [int(x) for x in old.split()[1:9]]
                    b = [int(x) for x in raw.split()[1:9]]
                    da, db_ = sum(a), sum(b)
                    ia = a[3] + (a[4] if len(a) > 4 else 0)
                    ib = b[3] + (b[4] if len(b) > 4 else 0)
                    if db_ > da:
                        entry["_cpu"] = round(max((1 - (ib - ia) / (db_ - da)) * 100, 0), 1)
                except Exception:
                    pass
        elif raw.startswith("NET "):
            rx, tx = (int(x) for x in raw.split()[1:3])
            if prev.get("rx") is not None and dt > 0:
                entry["_rx"] = round(max(rx - prev["rx"], 0) * 8 / 1000 / dt, 1)
                entry["_tx"] = round(max(tx - prev["tx"], 0) * 8 / 1000 / dt, 1)
            prev["rx"], prev["tx"] = rx, tx
        elif raw.startswith("DISK "):
            t_kb, u_kb = (int(x) for x in raw.split()[1:3])
            entry["_dtot"], entry["_dused"] = round(t_kb / 1048576, 1), round(u_kb / 1048576, 1)
        elif raw.startswith("MEM "):
            t_kb, a_kb = (int(x) for x in raw.split()[1:3])
            entry["_mtot"] = round(t_kb / 1024)
            entry["_mused"] = round(max(t_kb - a_kb, 0) / 1024)
        elif raw.startswith("OSINFO "):
            p = raw.split(" ", 1)[1].split("|")
            host = {"os": p[0] if p else "Linux",
                    "kernel": p[1] if len(p) > 1 else "",
                    "cores": int(p[2]) if len(p) > 2 and p[2].isdigit() else 4,
                    "hostname": p[3] if len(p) > 3 else "",
                    "public_ip": host.get("public_ip", "")}
        elif raw.startswith("PUBIP "):
            pub = raw.split(" ", 1)[1].strip() if len(raw.split(" ", 1)) > 1 else ""
            if pub:
                host["public_ip"] = pub

    prev["ct_cpu"] = ct_cpu_new
    entry["host"] = {"os": host["os"], "kernel": host["kernel"],
                     "cores": host["cores"], "hostname": host["hostname"],
                     "public_ip": host.get("public_ip", ""),
                     "cpu_pct": entry.pop("_cpu", 0.0),
                     "mem_total_mb": entry.pop("_mtot", 0),
                     "mem_used_mb": entry.pop("_mused", 0),
                     "disk_total_gb": entry.pop("_dtot", 0.0),
                     "disk_used_gb": entry.pop("_dused", 0.0),
                     "rx_kbps": entry.pop("_rx", 0.0),
                     "tx_kbps": entry.pop("_tx", 0.0)}
    return entry
