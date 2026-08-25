"""订阅链接生成：对标 X-UI-Server

* 面板级订阅 Token（settings 表，管理员可重置）
* GET /api/sub/{token}          → base64(分享链接列表)   （v2rayNG / Shadowrocket / NekoBox…）
* GET /api/sub/{token}?target=clash 或 UA 含 clash/mihomo/stash… → Clash.Meta(mihomo) YAML
* 数据源: apps 表 params.spec（部署时持久化的完整节点规格, 含密钥材料）
"""
import base64
import json

from . import db


# ┊ settings KV ┊
def get_setting(key: str) -> str | None:
    try:
        row = db.one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else None
    except Exception:
        return None


def set_setting(key: str, value: str):
    db.ex("INSERT INTO settings(key,value) VALUES(?,?) "
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", key, value)


def get_or_create_sub_token() -> str:
    tok = get_setting("sub_token")
    if not tok:
        import secrets as _s
        tok = _s.token_urlsafe(24)
        set_setting("sub_token", tok)
    return tok


def reset_sub_token() -> str:
    import secrets as _s
    tok = _s.token_urlsafe(24)
    set_setting("sub_token", tok)
    return tok


# ┊ 收集全部已部署节点规格 ┊
def collect_specs() -> list[dict]:
    """返回 [{...spec..., '_app': app名, '_ip': 公网IP}]，跳过没有 spec 的历史记录"""
    out = []
    for r in db.q("SELECT id, name, params, links FROM apps WHERE status='done' ORDER BY id"):
        try:
            params = json.loads(r["params"] or "{}")
        except Exception:
            continue
        spec = params.get("spec") or []
        if not spec:
            continue
        pub_ip = params.get("public_ip") or ""
        for n in spec:
            n = dict(n)
            n["_app"] = r["name"]
            n["_ip"] = pub_ip
            out.append(n)
    return out


def collect_links() -> list[str]:
    out = []
    for r in db.q("SELECT links FROM apps WHERE status='done' ORDER BY id"):
        try:
            out.extend(json.loads(r["links"] or "[]"))
        except Exception:
            continue
    return out


# ┊ Clash YAML 构建（mihomo / Clash.Meta 全协议） ┊
def _y(v) -> str:
    """YAML 双引号安全字符串"""
    s = str(v if v is not None else "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _clash_proxy(n: dict, name: str, ip: str) -> str | None:
    """把单个节点 spec 转成 Clash(mihomo) proxy 字典 YAML 片段"""
    proto, port, sni = n["protocol"], int(n["port"]), n.get("sni") or ""
    uuid_, pwd = n.get("uuid", ""), n.get("password", "")
    L = []

    def w(k, val, indent=4):
        L.append(f"{' '*indent}{k}: {_y(val)}")

    def wl(k, *vals, indent=4):
        L.append(f"{' '*indent}{k}:")
        for x in vals:
            L.append(f"{' '*(indent+2)}- {_y(x)}")

    if proto == "XTLS-Reality":
        L.append(f"  - name: {_y(name)}"); w("type", "vless"); w("server", ip); L.append(f"    port: {port}")
        w("uuid", uuid_); L.append("    udp: true"); L.append("    tls: true")
        w("flow", "xtls-rprx-vision"); w("servername", sni)
        w("client-fingerprint", "chrome")
        L.append("    reality-opts:"); w("public-key", n.get("public_key", ""), 6); w("short-id", n.get("short_id", ""), 6)
    elif proto == "Hysteria2":
        L.append(f"  - name: {_y(name)}"); w("type", "hysteria2"); w("server", ip); L.append(f"    port: {port}")
        w("password", uuid_ or pwd); w("sni", sni); L.append("    skip-cert-verify: true")
    elif proto == "TUIC":
        L.append(f"  - name: {_y(name)}"); w("type", "tuic"); w("server", ip); L.append(f"    port: {port}")
        w("uuid", uuid_); w("password", pwd); w("sni", sni)
        w("congestion-control", "bbr"); w("alpn", "h3"); L.append("    skip-cert-verify: true")
    elif proto == "Trojan":
        L.append(f"  - name: {_y(name)}"); w("type", "trojan"); w("server", ip); L.append(f"    port: {port}")
        w("password", pwd); w("sni", sni); w("skip-cert-verify", "true"); L.append("    udp: true")
    elif proto == "H2-Reality":
        L.append(f"  - name: {_y(name)}"); w("type", "vless"); w("server", ip); L.append(f"    port: {port}")
        w("uuid", uuid_); L.append("    udp: true"); L.append("    tls: true"); wl("alpn", "h2")
        w("servername", sni); w("client-fingerprint", "chrome"); w("network", "h2")
        L.append("    reality-opts:"); w("public-key", n.get("public_key", ""), 6); w("short-id", n.get("short_id", ""), 6)
        L.append("    h2-opts:"); wl("host", sni or ip, indent=6); w("path", "/", 6)
    elif proto == "gRPC-Reality":
        L.append(f"  - name: {_y(name)}"); w("type", "vless"); w("server", ip); L.append(f"    port: {port}")
        w("uuid", uuid_); L.append("    udp: true"); L.append("    tls: true"); wl("alpn", "h2")
        w("servername", sni); w("client-fingerprint", "chrome"); w("network", "grpc")
        L.append("    reality-opts:"); w("public-key", n.get("public_key", ""), 6); w("short-id", n.get("short_id", ""), 6)
        L.append("    grpc-opts:"); w("grpc-service-name", "grpc", 6)
    elif proto == "AnyTLS":
        L.append(f"  - name: {_y(name)}"); w("type", "anytls"); w("server", ip); L.append(f"    port: {port}")
        w("password", pwd); w("client-fingerprint", "chrome"); L.append("    udp: true")
        w("sni", sni); L.append("    skip-cert-verify: true")
    elif proto in ("VLESS-WS", "VMESS-WS"):
        t = "vless" if proto == "VLESS-WS" else "vmess"
        L.append(f"  - name: {_y(name)}"); w("type", t); w("server", ip); L.append(f"    port: {port}")
        w("uuid", uuid_)
        if t == "vmess":
            w("alterId", "0")
        L.append("    udp: true"); w("network", "ws")
        L.append("    ws-opts:"); w("path", "/", 6)
    elif proto == "SS-2022":
        L.append(f"  - name: {_y(name)}"); w("type", "ss"); w("server", ip); L.append(f"    port: {port}")
        w("cipher", "2022-blake3-aes-128-gcm"); w("password", pwd); L.append("    udp: true")
    elif proto == "Naive":
        # mihomo 不支持 naive 协议 → 跳过（base64 订阅里仍保留）
        return None
    else:
        return None
    return "\n".join(L) + "\n"


def build_clash_yaml(specs: list[dict], sub_title="LXCDeck") -> str:
    proxies, names = [], []
    used = set()
    for i, n in enumerate(specs):
        base = f"{n.get('_app', 'node')}-{n['protocol']}"
        nm, k = base, 2
        while nm in used:
            nm, k = f"{base}#{k}", k + 1
        used.add(nm)
        p = _clash_proxy(n, nm, n["_ip"])
        if p:
            proxies.append(p.rstrip("\n"))
            names.append(nm)

    names_yaml = "\n".join(f"      - {_y(x)}" for x in names) if names else "      - DIRECT"
    return f"""# {sub_title} · Clash.Meta / mihomo 订阅
# 由 LXC Deck 自动生成  ({len(names)} 个节点)
port: 7890
socks-port: 7891
allow-lan: false
mode: rule
log-level: info
ipv6: false
external-controller: 127.0.0.1:9090

proxies:
{chr(10).join(proxies) if proxies else '  # (无节点)'}

proxy-groups:
  - name: "PROXY"
    type: select
    proxies:
      - "AUTO"
{names_yaml}
  - name: "AUTO"
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50
    proxies:
{names_yaml}

rules:
  - GEOIP,CN,DIRECT
  - MATCH,PROXY
"""


def render_subscription(user_agent: str = "", target: str = "") -> tuple[str, str, str]:
    """返回 (body, content_type, disposition)。target: ''|'clash'|'base64'"""
    ua = (user_agent or "").lower()
    wants_clash = target == "clash" or (not target and any(
        k in ua for k in ("clash", "mihomo", "stash", "sing-box", "karing",
                          "flclash", "verge", "cfw")))
    specs = collect_specs()
    if wants_clash:
        yaml_text = build_clash_yaml(specs)
        return yaml_text, "text/yaml; charset=utf-8", "attachment; filename=lxcdeck-clash.yaml"
    # base64 模式优先用持久化链接（含 naive 等所有协议）
    links = collect_links()
    if not links:
        links = []
    body = base64.b64encode("\n".join(links).encode()).decode()
    return body, "text/plain; charset=utf-8", ""
