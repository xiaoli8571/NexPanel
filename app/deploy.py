"""一键应用部署：把 X-UI-Server 的节点下发能力移植到 LXC 容器内

* 8合1 全家桶: XTLS-Reality / Hysteria2 / TUIC / Trojan / H2-Reality /
               gRPC-Reality / AnyTLS / Naive （起始端口连续 8 个, 共用 UUID）
* 单节点:     上述任一 + VLESS-WS / VMess-WS / SS-2022
* 落地形态:   sing-box 跑在指定 LXC 容器内; 面板自动在宿主节点加 DNAT 端口映射
"""
import base64
import json
import secrets
import time

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey)

DEFAULT_SNI = "addons.mozilla.org"
SNI_PRESETS = ["addons.mozilla.org", "www.apple.com", "gateway.icloud.com",
               "itunes.apple.com", "www.microsoft.com", "www.yahoo.com"]

# ────────────── 协议定义(端口偏移, 是否 Reality, 传输层, 是否需要 TLS 证书) ──────────────
PROTOCOL_SEQ = [
    {"protocol": "XTLS-Reality", "offset": 0, "sni": DEFAULT_SNI, "reality": True,  "net": "tcp"},
    {"protocol": "Hysteria2",    "offset": 1, "sni": DEFAULT_SNI, "tls": True,       "udp": True},
    {"protocol": "TUIC",         "offset": 2, "sni": DEFAULT_SNI, "tls": True,       "udp": True},
    {"protocol": "Trojan",       "offset": 3, "sni": DEFAULT_SNI, "tls": True},
    {"protocol": "H2-Reality",   "offset": 4, "sni": DEFAULT_SNI, "reality": True,   "net": "http"},
    {"protocol": "gRPC-Reality", "offset": 5, "sni": DEFAULT_SNI, "reality": True,   "net": "grpc"},
    {"protocol": "AnyTLS",       "offset": 6, "sni": DEFAULT_SNI, "tls": True},
    {"protocol": "Naive",        "offset": 7, "sni": DEFAULT_SNI, "tls": True},
]
CATALOG = {
    "xui-8in1": {"label": "🚀 极速全量节点下发 (8合1)",
                 "desc": "XTLS+Reality, Hysteria2, TUIC, Trojan, H2+Reality, gRPC+Reality, AnyTLS, Naive — 起始端口起连续 8 个，共用 UUID，FSCARMEN 模式",
                 "multi": True},
    "xtls-reality": {"label": "XTLS + Reality", "single": PROTOCOL_SEQ[0]},
    "hysteria2":    {"label": "Hysteria2 (极速)", "single": PROTOCOL_SEQ[1]},
    "tuic":         {"label": "TUIC v5 (高并发)", "single": PROTOCOL_SEQ[2]},
    "trojan":       {"label": "Trojan", "single": PROTOCOL_SEQ[3]},
    "h2-reality":   {"label": "H2 + Reality", "single": PROTOCOL_SEQ[4]},
    "grpc-reality": {"label": "gRPC + Reality", "single": PROTOCOL_SEQ[5]},
    "anytls":       {"label": "AnyTLS", "single": PROTOCOL_SEQ[6]},
    "naive":        {"label": "Naive", "single": PROTOCOL_SEQ[7]},
    "vless-ws":     {"label": "VLESS + WS", "single": {"protocol": "VLESS-WS"}},
    "vmess-ws":     {"label": "VMess + WS", "single": {"protocol": "VMESS-WS"}},
    "ss-2022":      {"label": "Shadowsocks 2022", "single": {"protocol": "SS-2022"}},
}


def reality_keypair() -> tuple[str, str]:
    """xray 兼容 x25519 密钥对(base64url)"""
    priv = X25519PrivateKey.generate()
    raw_priv = priv.private_bytes_raw()
    raw_pub = priv.public_key().public_bytes_raw()
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
    return b64(raw_priv), b64(raw_pub)


def short_id() -> str:
    return secrets.token_hex(4)


def gen_uuid() -> str:
    import uuid as u
    return str(u.uuid4())


def build_nodes_spec(app_type: str, start_port: int, sni: str) -> list[dict]:
    """生成节点规格列表(含密钥材料) —— 对应 X-UI deployAllProtocols 的 payload 组装"""
    sni = sni or DEFAULT_SNI
    common_uuid = gen_uuid()
    if app_type == "xui-8in1":
        seq = PROTOCOL_SEQ
    elif app_type in CATALOG and CATALOG[app_type].get("single"):
        seq = [dict(CATALOG[app_type]["single"])]
    else:
        raise ValueError(f"未知应用类型 {app_type}")
    multi = app_type == "xui-8in1"
    nodes = []
    for i, item in enumerate(seq):
        n = {"id": f"n{secrets.token_hex(4)}",
             "protocol": item["protocol"],
             "port": start_port + (item.get("offset", 0) if multi else 0),
             "uuid": common_uuid,
             "sni": item.get("sni") or sni,
             "network": item.get("net", "tcp")}
        if item.get("reality"):
            n["private_key"], n["public_key"] = reality_keypair()
            n["short_id"] = short_id()
        elif item["protocol"] == "Naive":
            n["password"] = common_uuid.replace("-", "")[:16]
        elif item["protocol"] == "SS-2022":
            n["password"] = base64.b64encode(secrets.token_bytes(16)).decode()  # 2022-blake3-aes-128-gcm
        else:
            n["password"] = base64.b64encode(secrets.token_bytes(16)).decode().rstrip("=")
        if item.get("tls") and not item.get("reality"):
            n["need_cert"] = True
        nodes.append(n)
    return nodes


def build_singbox_config(nodes_spec: list[dict], cert_path="/etc/sing-box/cert.pem",
                         key_path="/etc/sing-box/key.pem") -> dict:
    """移植自 X-UI-Server agent.build_singbox_config 的 inbound 部分"""
    conf = {"log": {"level": "warn"}, "inbounds": [],
            "outbounds": [{"type": "direct", "tag": "direct-out"}],
            "route": {"rules": []}}
    for i, n in enumerate(nodes_spec):
        tag, proto, port = f"in-{i+1}", n["protocol"], int(n["port"])
        sni, uuid_, pwd = n.get("sni"), n["uuid"], n.get("password", "")
        base = {"tag": tag, "listen": "::", "listen_port": port}
        if proto == "VLESS-WS":
            conf["inbounds"].append({**base, "type": "vless",
                "users": [{"uuid": uuid_}],
                "transport": {"type": "ws", "path": "/"}})
        elif proto == "VMESS-WS":
            conf["inbounds"].append({**base, "type": "vmess",
                "users": [{"uuid": uuid_, "alterId": 0}],
                "transport": {"type": "ws", "path": "/"}})
        elif proto == "SS-2022":
            conf["inbounds"].append({**base, "type": "shadowsocks",
                "method": "2022-blake3-aes-128-gcm", "password": pwd})
        elif proto in ("XTLS-Reality",):
            conf["inbounds"].append({**base, "type": "vless",
                "users": [{"uuid": uuid_, "flow": "xtls-rprx-vision"}],
                "tls": {"enabled": True, "server_name": sni,
                        "reality": {"enabled": True,
                                    "handshake": {"server": sni, "server_port": 443},
                                    "private_key": n["private_key"],
                                    "short_id": [n["short_id"]]}}})
        elif proto == "Hysteria2":
            conf["inbounds"].append({**base, "type": "hysteria2",
                "users": [{"password": uuid_}],
                "tls": {"enabled": True, "alpn": ["h3"],
                        "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "TUIC":
            conf["inbounds"].append({**base, "type": "tuic",
                "users": [{"uuid": uuid_, "password": pwd}],
                "congestion_control": "bbr",
                "tls": {"enabled": True, "alpn": ["h3"],
                        "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "Trojan":
            conf["inbounds"].append({**base, "type": "trojan",
                "users": [{"password": pwd}],
                "tls": {"enabled": True, "server_name": sni,
                        "certificate_path": cert_path, "key_path": key_path}})
        elif proto == "H2-Reality":
            conf["inbounds"].append({**base, "type": "vless",
                "users": [{"uuid": uuid_}],
                "tls": {"enabled": True, "server_name": sni, "alpn": ["h2", "http/1.1"],
                        "reality": {"enabled": True,
                                    "handshake": {"server": sni, "server_port": 443},
                                    "private_key": n["private_key"],
                                    "short_id": [n["short_id"]]}},
                "transport": {"type": "http", "host": [sni], "path": "/"}})
        elif proto == "gRPC-Reality":
            conf["inbounds"].append({**base, "type": "vless",
                "users": [{"uuid": uuid_}],
                "tls": {"enabled": True, "server_name": sni, "alpn": ["h2"],
                        "reality": {"enabled": True,
                                    "handshake": {"server": sni, "server_port": 443},
                                    "private_key": n["private_key"],
                                    "short_id": [n["short_id"]]}},
                "transport": {"type": "grpc", "service_name": "grpc"}})
        elif proto == "AnyTLS":
            conf["inbounds"].append({**base, "type": "anytls",
                "users": [{"password": pwd}],
                "tls": {"enabled": True, "certificate_path": cert_path,
                        "key_path": key_path}})
        elif proto == "Naive":
            conf["inbounds"].append({**base, "type": "naive",
                "users": [{"username": uuid_, "password": pwd}],
                "tls": {"enabled": True, "certificate_path": cert_path,
                        "key_path": key_path}})
    return conf


# ────────────── 分享链接(对应 X-UI 前端 sub 生成逻辑) ──────────────
def build_links(nodes_spec, ip: str, name_prefix: str) -> list[str]:
    from urllib.parse import quote
    links = []
    for n in nodes_spec:
        proto, port, sni = n["protocol"], n["port"], n.get("sni") or DEFAULT_SNI
        remark = quote(f"{name_prefix}-{proto}-{port}", safe="")
        pbk, sid = n.get("public_key", ""), n.get("short_id", "")
        if proto == "XTLS-Reality":
            links.append(f"vless://{n['uuid']}@{ip}:{port}?type=tcp&security=reality"
                         f"&pbk={pbk}&fp=chrome&sni={quote(sni)}&sid={sid}"
                         f"&flow=xtls-rprx-vision#{remark}")
        elif proto == "Hysteria2":
            links.append(f"hysteria2://{quote(n['uuid'])}@{ip}:{port}/"
                         f"?insecure=1&sni={quote(sni)}&alpn=h3#{remark}")
        elif proto == "TUIC":
            links.append(f"tuic://{n['uuid']}:{quote(n['password'])}@{ip}:{port}"
                         f"?sni={quote(sni)}&congestion_control=bbr&alpn=h3"
                         f"&insecure=1#{remark}")
        elif proto == "Trojan":
            links.append(f"trojan://{quote(n['password'])}@{ip}:{port}"
                         f"?security=tls&sni={quote(sni)}&insecure=1#{remark}")
        elif proto == "H2-Reality":
            links.append(f"vless://{n['uuid']}@{ip}:{port}?type=http&security=reality"
                         f"&pbk={pbk}&fp=chrome&sni={quote(sni)}&sid={sid}#{remark}")
        elif proto == "gRPC-Reality":
            links.append(f"vless://{n['uuid']}@{ip}:{port}?type=grpc"
                         f"&serviceName=grpc&security=reality&pbk={pbk}&fp=chrome"
                         f"&sni={quote(sni)}&sid={sid}#{remark}")
        elif proto == "AnyTLS":
            links.append(f"anytls://{quote(n['password'])}@{ip}:{port}"
                         f"?insecure=1&sni={quote(sni)}#{remark}")
        elif proto == "Naive":
            links.append(f"naive+https://{n['uuid']}:{quote(n['password'])}@{ip}:{port}"
                         f"?sni={quote(sni)}#{remark}")
        elif proto == "VLESS-WS":
            links.append(f"vless://{n['uuid']}@{ip}:{port}?type=ws&path=%2F"
                         f"&host={quote(ip)}#{remark}")
        elif proto == "VMESS-WS":
            vm = {"v": "2", "ps": remark, "add": ip, "port": str(port),
                  "id": n["uuid"], "aid": "0", "net": "ws", "path": "/",
                  "host": ip, "tls": ""}
            links.append("vmess://" + base64.b64encode(
                json.dumps(vm).encode()).decode())
        elif proto == "SS-2022":
            userinfo = base64.b64encode(
                f"2022-blake3-aes-128-gcm:{n['password']}".encode()).decode()
            links.append(f"ss://{userinfo}@{ip}:{port}#{remark}")
    return links


# ────────────── 在容器内落地 sing-box 的脚本 ──────────────
def container_install_script(config_json: dict) -> str:
    cfg_b64 = base64.b64encode(json.dumps(config_json).encode()).decode()
    return r'''
set -e
ARCH=$(uname -m); case "$ARCH" in x86_64|amd64) SB_ARCH=amd64;; aarch64) SB_ARCH=arm64;; *) SB_ARCH=amd64;; esac
VER=1.12.8
PKG=""
if command -v apt-get >/dev/null 2>&1; then PKG=apt; fi
if command -v apk >/dev/null 2>&1; then PKG=apk; fi
ensure_pkg() {
  need=""
  command -v curl >/dev/null 2>&1 || need="$need curl"
  command -v openssl >/dev/null 2>&1 || need="$need openssl"
  command -v tar >/dev/null 2>&1 || need="$need tar"
  [ -z "$need" ] && return 0
  if [ "$PKG" = apt ]; then
    apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl openssl ca-certificates tar
  elif [ "$PKG" = apk ]; then
    apk add --no-cache curl openssl ca-certificates tar libstdc++
  fi
}
ensure_pkg
NEED_DL=1
if [ -x /usr/local/bin/sing-box ]; then
  CUR=$(/usr/local/bin/sing-box version 2>/dev/null | head -n1 | awk '{print $3}')
  [ "$CUR" = "$VER" ] && NEED_DL=0
fi
if [ "$NEED_DL" = "1" ]; then
  rm -f /tmp/sb.tgz
  for i in 1 2 3; do
    curl -fSL --retry 2 --connect-timeout 15 \
      "https://github.com/SagerNet/sing-box/releases/download/v${VER}/sing-box-${VER}-linux-${SB_ARCH}.tar.gz" \
      -o /tmp/sb.tgz && break
    sleep 3
  done
  [ -s /tmp/sb.tgz ] || { echo "[FAIL] sing-box 下载失败"; exit 1; }
  tar -C /tmp -xzf /tmp/sb.tgz
  install -m755 "/tmp/sing-box-${VER}-linux-${SB_ARCH}/sing-box" /usr/local/bin/sing-box
fi
mkdir -p /etc/sing-box
[ -f /etc/sing-box/cert.pem ] || openssl req -x509 -newkey ec \
  -pkeyopt ec_paramgen_curve:prime256v1 -keyout /etc/sing-box/key.pem \
  -out /etc/sing-box/cert.pem -days 3650 -nodes -subj "/CN=bing.com" >/dev/null 2>&1
''' + f'echo {cfg_b64!r} | base64 -d > /etc/sing-box/config.json\n' + r'''
if command -v systemctl >/dev/null 2>&1; then
  cat > /etc/systemd/system/sing-box.service <<UNIT
[Unit]
Description=sing-box (LXC Deck)
After=network.target
[Service]
ExecStart=/usr/local/bin/sing-box run -c /etc/sing-box/config.json
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now sing-box
elif command -v rc-service >/dev/null 2>&1; then
  cat > /etc/init.d/sing-box <<'RC'
#!/sbin/openrc-run
command="/usr/local/bin/sing-box"
command_args="run -c /etc/sing-box/config.json"
pidfile="/run/singbox.pid"
command_background="yes"
RC
  chmod +x /etc/init.d/sing-box
  rc-update add sing-box default >/dev/null 2>&1 || true
  rc-service sing-box restart || rc-service sing-box start
else
  pkill -f "sing-box run" 2>/dev/null || true
  nohup /usr/local/bin/sing-box run -c /etc/sing-box/config.json >/var/log/singbox.log 2>&1 &
fi
sleep 1.5
if pidof sing-box >/dev/null 2>&1 || (command -v systemctl >/dev/null && systemctl is-active sing-box >/dev/null); then
  echo "[OK] sing-box running"
else
  echo "[FAIL] sing-box not running"; exit 1
fi
'''


# ══════════════ 任务执行器(面板侧) ══════════════
import asyncio
from . import db, monitor

JOBS: dict[str, dict] = {}          # job_id -> {status, log[], result, app_id}


def job_snapshot(job_id: str) -> dict | None:
    j = JOBS.get(job_id)
    if not j:
        return None
    return {"job_id": job_id, "status": j["status"],
            "log": "".join(j["log"])[-16000:],
            "result": j.get("result"), "app_id": j.get("app_id")}


def _log(j, line: str):
    j["log"].append(line + "\n")
    print(f"[deploy:{j['id']}] {line}", flush=True)


def _node_public_ip(node: dict) -> str:
    entry = monitor.get_cache(node["id"]) or {}
    host = entry.get("host") or {}
    return (node.get("public_ip") or host.get("public_ip")
            or host.get("hostname") or node.get("host") or "")


async def _exec_on_node(node: dict, script_b64_content: str, j, timeout=600) -> tuple[int, str]:
    """节点级执行: agent → 命令队列; ssh → paramiko"""
    from . import nodes as nodes_mod
    kind = node["kind"]
    from . import agent as agent_mod
    if kind == "agent":
        if not monitor.agent_online(node["id"]):
            raise RuntimeError("Agent 离线，无法下发")
        cid = agent_mod.queue_exec(node["id"], script_b64_content, timeout=timeout)
        res = await asyncio.to_thread(agent_mod.wait_result, cid, timeout + 30)
        if res is None:
            raise RuntimeError("Agent 执行超时")
        return res["rc"], res["out"]
    elif kind == "ssh":
        import base64 as b64mod
        wrapped = f"echo {b64mod.b64encode(script_b64_content.encode()).decode()} | base64 -d | bash"
        rc, out = await asyncio.to_thread(nodes_mod.run_cmd, node, wrapped, timeout)
        return rc, out
    else:
        raise RuntimeError(f"节点类型 {kind} 不支持部署")


async def run_deploy(job_id: str, container: dict | None, node: dict,
                     spec: list[dict], sni: str, name_prefix: str,
                     host_target: bool = False):
    j = JOBS[job_id]
    cname = (container or {}).get("name", "")
    cip = ""
    dnat_rules = []
    try:
        j["status"] = "running"
        if host_target:
            _log(j, f"[1] 目标模式：主机直装（{node['name']}）— 端口直接绑定宿主")
        else:
            row = db.one("SELECT status FROM containers WHERE id=?", (container["id"],))
            if row and row["status"] != "running":
                _log(j, f"[1] 启动容器 {cname} …")
                from .lxc import ops_for
                ops = ops_for(node)
                if node["kind"] == "demo":
                    ops.start(container)
                else:
                    ops.start(node, container)
                db.ex("UPDATE containers SET status='running' WHERE id=?", (container["id"],))
                await asyncio.sleep(3)

            # 获取容器 IP
            getip = f'lxc-info -iH -n "{cname}"'
            rc, out = await _exec_on_node(node, getip, j, 60)
            cip = out.strip().splitlines()[0] if out.strip() else ""
            if not cip:
                raise RuntimeError(f"未获取到容器 IP: {out[-200:]}")
            _log(j, f"    容器 IP = {cip}")

        # 生成 sing-box 配置并写入/启动
        conf = build_singbox_config(spec)
        script = container_install_script(conf)
        import base64 as b64mod
        inner = b64mod.b64encode(script.encode()).decode()
        if host_target:
            _log(j, f"[3] 在主机安装 sing-box 并配置 {len(spec)} 个入站 …")
            wrapper = f"printf %s {inner} | base64 -d | bash"
        else:
            _log(j, f"[3] 在容器内安装 sing-box 并配置 {len(spec)} 个入站 …")
            wrapper = (f'printf %s {inner} | base64 -d | '
                       f'lxc-attach -n "{cname}" -- bash -s')
        rc, out = await _exec_on_node(node, wrapper, j, 900)
        if rc != 0 and "bash" in out:
            _log(j, "    容器无 bash，改用 sh …")
            wrapper_sh = wrapper.replace("-- bash -s", "-- sh -s")
            # sh 不支持部分 bashism，脚本本身保持 POSIX
            rc, out = await _exec_on_node(node, wrapper_sh, j, 900)
        for ln in out.splitlines():
            if ln.strip():
                _log(j, "    " + ln[:150])
        if "[OK]" not in out:
            raise RuntimeError(f"容器内部署失败(rc={rc})")

        # 3) 宿主侧 DNAT 映射（仅容器模式需要）
        dnat_rules = []
        if host_target:
            _log(j, "[4] 主机直装无需端口映射")
        else:
            _log(j, "[4] 配置宿主端口转发(DNAT) …")
            for n in spec:
                proto_flag = "-p udp" if n["protocol"] in ("Hysteria2", "TUIC") else "-p tcp"
                dport = n["port"]
                rules = [
                    f"iptables -t nat -A PREROUTING {proto_flag} --dport {dport} "
                    f"-j DNAT --to-destination {cip}:{dport}",
                    f"iptables -t nat -A POSTROUTING {proto_flag} -d {cip} "
                    f"-j MASQUERADE",
                ]
                for cmd in [r for r in rules if r]:
                    rc2, o2 = await _exec_on_node(node, cmd + " 2>/dev/null || true", j, 30)
                dnat_rules.append({"proto": "udp" if n["protocol"] in ("Hysteria2", "TUIC") else "tcp",
                                   "dport": dport, "to": f"{cip}:{dport}"})
            _log(j, f"    已映射 {len(dnat_rules)} 个端口 → {cip}")

        # 4) 生成分享链接
        pub = _node_public_ip(node) or "NODE_IP"
        links = build_links(spec, pub, name_prefix)
        _log(j, f"[5] 部署完成！生成 {len(links)} 条分享链接")
        j["status"] = "done"
        j["result"] = {"links": links, "container_ip": cip, "public_ip": pub}

        # 持久化
        db.ex("""INSERT INTO apps(container_id,node_id,name,app_type,params,links,dnat_rules,status,log,created_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (container or {}).get("id"), node["id"], name_prefix, "proxy",
              json.dumps({"spec": [{k: v for k, v in n.items()} for n in spec],
                          "public_ip": pub, "container_ip": cip}, ensure_ascii=False),
              json.dumps(links, ensure_ascii=False),
              json.dumps(dnat_rules), "done", "".join(j["log"]), db.now())
        app_id = db.one("SELECT id FROM apps ORDER BY id DESC LIMIT 1")["id"]
        j["app_id"] = app_id

    except Exception as e:
        j["status"] = "failed"
        j["result"] = {"error": str(e)[:300]}
        _log(j, f"✗ 失败: {e}")
        try:
            db.ex("""INSERT INTO apps(container_id,name,app_type,status,log,created_at)
                     VALUES(?,?,?,?,?,?)""",
                  container["id"], name_prefix, "proxy", "failed",
                  "".join(j["log"])[-4000:], db.now())
        except Exception:
            pass


async def start_deploy(target_type: str, app_type: str, start_port: int,
                       sni: str, user: dict, ip: str,
                       container_id: int | None = None,
                       node_id: int | None = None) -> str:
    """target_type: 'container'(部署进 LXC) | 'host'(VPS 主机直装)"""
    if target_type == "host":
        node_row = db.one("SELECT * FROM nodes WHERE id=?", (node_id,))
        if not node_row:
            raise ValueError("节点不存在")
        node = dict(node_row)
        if node["kind"] == "demo":
            raise ValueError("演示节点不支持部署")
        if node["kind"] == "agent":
            from . import agent as agent_mod
            if not agent_mod.is_online(node["id"]):
                raise ValueError("Agent 离线，无法下发")
        container = None
        name_prefix = node["name"]
    else:
        row = db.one("SELECT * FROM containers WHERE id=?", (container_id,))
        if not row:
            raise ValueError("容器不存在")
        container = dict(row)
        node_row = db.one("SELECT * FROM nodes WHERE id=?", (container["node_id"],))
        if not node_row:
            raise ValueError("容器未关联有效节点")
        node = dict(node_row)
        name_prefix = container["name"]

    if app_type != "xui-8in1" and app_type not in CATALOG:
        raise ValueError(f"未知应用 {app_type}")

    spec = build_nodes_spec(app_type, start_port, sni)
    job_id = "job_" + secrets.token_hex(6)
    JOBS[job_id] = {"id": job_id, "status": "pending", "log": [], "result": None}
    db.audit(user["sub"], "一键部署", name_prefix,
             f"{app_type} @:{start_port} ({target_type})", ip)

    async def _run():
        await run_deploy(job_id, container, node, spec, sni, name_prefix,
                         host_target=(target_type == "host"))

    asyncio.get_running_loop().create_task(_run())
    return job_id


async def _apply_singbox_config(node: dict, container: dict | None, conf: dict,
                               host_target: bool, j: dict) -> tuple[int, str]:
    """把 sing-box 配置下发到目标（主机直装 或 容器内），并重启服务"""
    script = container_install_script(conf)
    inner = base64.b64encode(script.encode()).decode()
    if host_target:
        wrapper = f"printf %s {inner} | base64 -d | bash"
    else:
        cname = (container or {}).get("name", "")
        wrapper = f"printf %s {inner} | base64 -d | lxc-attach -n \"{cname}\" -- bash -s"
    rc, out = await _exec_on_node(node, wrapper, j, 900)
    if rc != 0 and "bash" in out:
        wrapper = wrapper.replace("-- bash -s", "-- sh -s")
        rc, out = await _exec_on_node(node, wrapper, j, 900)
    return rc, out


async def remove_app(app_id: int, user: dict, ip: str):
    a = db.one("SELECT * FROM apps WHERE id=?", (app_id,))
    if not a:
        raise ValueError("应用不存在")
    c = db.one("SELECT * FROM containers WHERE id=?", (a["container_id"],)) if a["container_id"] else None
    node = db.one("SELECT * FROM nodes WHERE id=?", (a["node_id"],)) if a["node_id"] else (db.one("SELECT * FROM nodes WHERE id=?", (c["node_id"],)) if c else None)
    # 反删 DNAT
    if node and node["kind"] in ("agent", "ssh"):
        for r in json.loads(a["dnat_rules"] or "[]"):
            proto = "-p udp" if r["proto"] == "udp" else "-p tcp"
            script = (f"iptables -t nat -D PREROUTING {proto} --dport {r['dport']} "
                      f"-j DNAT --to-destination {r['to']} 2>/dev/null; true")
            try:
                await _exec_on_node(dict(node), script, {"id":"rm","log":[],"status":"","result":None}, 30)
            except Exception:
                pass
    # 容器内停服务
    if c and node:
        try:
            await _exec_on_node(dict(node),
                f'lxc-attach -n "{c["name"]}" -- systemctl disable --now sing-box; true',
                {"id":"rm","log":[],"status":"","result":None}, 60)
        except Exception:
            pass
    db.ex("DELETE FROM apps WHERE id=?", (app_id,))
    db.audit(user["sub"], "删除应用", a["name"], "", ip)


async def remove_single_node(app_id: int, index: int, user: dict, ip: str):
    """删除某个应用(8合1/单协议)中的单个代理节点：更新配置 → 重启 sing-box → 移除DNAT → 更新DB"""
    a = db.one("SELECT * FROM apps WHERE id=?", (app_id,))
    if not a:
        raise ValueError("应用不存在")
    try:
        params = json.loads(a["params"] or "{}")
        spec = params.get("spec") or []
        links = json.loads(a["links"] or "[]")
        dnat = json.loads(a["dnat_rules"] or "[]")
    except Exception:
        raise ValueError("应用数据损坏")
    if index < 0 or index >= len(spec):
        raise ValueError("节点不存在")
    removed = spec.pop(index)
    if index < len(links):
        links.pop(index)
    removed_dnat = [r for r in dnat if r.get("dport") == removed.get("port")]
    dnat = [r for r in dnat if r.get("dport") != removed.get("port")]

    c = db.one("SELECT * FROM containers WHERE id=?", (a["container_id"],)) if a["container_id"] else None
    node = db.one("SELECT * FROM nodes WHERE id=?", (a["node_id"],)) if a["node_id"] else (db.one("SELECT * FROM nodes WHERE id=?", (c["node_id"],)) if c else None)
    if node and node["kind"] in ("agent", "ssh"):
        for r in removed_dnat:
            proto = "-p udp" if r["proto"] == "udp" else "-p tcp"
            script = (f"iptables -t nat -D PREROUTING {proto} --dport {r['dport']} "
                      f"-j DNAT --to-destination {r['to']} 2>/dev/null; true")
            try:
                await _exec_on_node(dict(node), script, {"id":"rm","log":[],"status":"","result":None}, 30)
            except Exception:
                pass

    if spec:
        # 还有剩余节点：重新生成配置并重启
        conf = build_singbox_config(spec)
        host_target = a["container_id"] is None
        rc, out = await _apply_singbox_config(node, c, conf, host_target,
                                              {"id":"rm","log":[],"status":"","result":None})
        if "[OK]" not in out:
            raise ValueError(f"远端更新失败: {out[-200:]}")
        params["spec"] = spec
        db.ex("UPDATE apps SET params=?, links=?, dnat_rules=? WHERE id=?",
              (json.dumps(params, ensure_ascii=False),
               json.dumps(links, ensure_ascii=False),
               json.dumps(dnat), app_id))
        db.audit(user["sub"], "删除节点",
                 f"{a['name']} - {removed.get('protocol')}@{removed.get('port')}", "", ip)
        return {"ok": True, "app_deleted": False}

    # 节点已删光 → 整条应用删除（含停止 sing-box）
    await remove_app(app_id, user, ip)
    db.audit(user["sub"], "删除节点",
             f"{a['name']} - {removed.get('protocol')}@{removed.get('port')} (最后节点，应用已删除)", "", ip)
    return {"ok": True, "app_deleted": True}
