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


# ┊ 订阅流量显示（Clash subscription-userinfo） ┊
DEFAULT_TOTAL_GB = 9999
_GIB = 1024 ** 3


def _sub_used_bytes() -> tuple[int, int]:
    """订阅「已使用」真实流量：只统计订阅内节点（有 status='done' 应用的节点，
    与 collect_specs 同口径）的 traffic_daily 汇总。返回 (upload=Σtx, download=Σrx)。"""
    try:
        row = db.one(
            "SELECT SUM(t.tx_bytes) AS tx, SUM(t.rx_bytes) AS rx FROM traffic_daily t "
            "WHERE t.node_id IN (SELECT DISTINCT node_id FROM apps "
            "                    WHERE status='done' AND node_id IS NOT NULL)")
        if row:
            return int(row["tx"] or 0), int(row["rx"] or 0)
    except Exception:
        pass          # 表不存在（未初始化流量统计）等场景 → 视为 0
    return 0, 0


def get_sub_traffic() -> dict:
    """面板订阅流量显示设置 {'remaining_gb': float|None, 'expire': str, 'used_gb': float}"""
    rem = get_setting("sub_userinfo_remaining")
    try:
        rem = float(rem) if rem not in (None, "") else None
    except (TypeError, ValueError):
        rem = None
    up, down = _sub_used_bytes()
    return {"remaining_gb": rem, "expire": get_setting("sub_userinfo_expire") or "",
            "used_gb": round((up + down) / _GIB, 2)}


def set_sub_traffic(remaining_gb, expire: str = ""):
    """流量重置：remaining_gb=None 清除手动设置（回退默认 9999G）"""
    set_setting("sub_userinfo_remaining",
                "" if remaining_gb in (None, "") else str(remaining_gb))
    set_setting("sub_userinfo_expire", (expire or "").strip())


def userinfo_header() -> str:
    """subscription-userinfo 头（客户端「已使用」= upload+download）。

    已使用 = 订阅内节点真实流量统计；
    手动剩余流量 → total = 已使用 + 剩余（客户端「剩余」显示手动值、「已使用」显示真实值）；
    留空 → total = 9999G（剩余 = 9999G - 已使用，随用量递减）。"""
    t = get_sub_traffic()
    up, down = _sub_used_bytes()
    used = up + down
    exp = f"; expire={_expire_epoch(t['expire'])}" if t["expire"] else ""
    if t["remaining_gb"] is not None:
        total = used + max(1, int(t["remaining_gb"] * _GIB))
    else:
        total = max(DEFAULT_TOTAL_GB * _GIB, used + _GIB)   # 剩余恒 ≥1G，防负数
    return f"upload={up}; download={down}; total={total}{exp}"


def _expire_epoch(expire: str) -> int:
    """'YYYY-MM-DD'（按东八区零点）→ epoch 秒；无效返回 0"""
    try:
        import calendar
        import datetime
        d = datetime.datetime.strptime((expire or "").strip(), "%Y-%m-%d")
        return calendar.timegm(d.timetuple()) - 8 * 3600
    except Exception:
        return 0


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
        cf_entry = ""
        if any(n.get("protocol") == "VLESS-WS-CF" for n in spec):
            try:
                from . import deploy as deploy_mod
                cf_entry = (deploy_mod.get_cf_entry() or "").strip()
            except Exception:
                cf_entry = ""
        egd = params.get("egress") or {}
        eg = egd.get("mode", "native")
        eg_tag = {"warp_ipv4": "WARP·v4", "warp_ipv6": "WARP·v6",
                  "warp_dual": "WARP·双栈"}.get(eg, "")
        if eg == "residential":
            eg_tag = ("住宅·" + (egd.get("country") or "").upper()) if egd.get("country") else "住宅"
        for n in spec:
            n = dict(n)
            n["_app"] = r["name"]
            n["_ip"] = pub_ip
            if n.get("protocol") == "VLESS-WS-CF" and cf_entry:
                n["entry"] = cf_entry  # 优选入口渲染时生效，改设置无需重新部署
            if eg_tag:
                n["_egress"] = eg_tag
            out.append(n)
    return out


def collect_links() -> list[str]:
    out = []
    for r in db.q("SELECT name, params, links FROM apps WHERE status='done' ORDER BY id"):
        try:
            links = json.loads(r["links"] or "[]")
        except Exception:
            continue
        # CF 隧道节点按当前优选入口重建链接（改设置即时生效）
        try:
            params = json.loads(r["params"] or "{}")
            spec = params.get("spec") or []
        except Exception:
            spec = []
        if any(n.get("protocol") == "VLESS-WS-CF" for n in spec):
            try:
                from . import deploy as deploy_mod
                spec2 = [dict(n) for n in spec]
                deploy_mod.apply_cf_entry(spec2)
                links = deploy_mod.build_links(spec2, params.get("public_ip") or "", r["name"])
            except Exception:
                pass
        out.extend(links)
    # VMess 已弃用：历史存量 vmess:// 链接一律不再下发
    return [l for l in out if not str(l).startswith("vmess://")]


# ┊ Clash YAML 构建（mihomo / Clash.Meta 全协议） ┊
def _y(v) -> str:
    """YAML 双引号安全字符串"""
    s = str(v if v is not None else "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _clash_proxy(n: dict, name: str, ip: str) -> str | None:
    """把单个节点 spec 转成 Clash(mihomo) proxy 字典 YAML 片段"""
    proto, port, sni = n["protocol"], int(n["port"]), n.get("sni") or ""
    if proto == "VMESS-WS":
        return None  # VMess 已弃用：不输出到订阅（存量节点自动过滤）
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
    elif proto == "VLESS-WS":
        L.append(f"  - name: {_y(name)}"); w("type", "vless"); w("server", ip); L.append(f"    port: {port}")
        w("uuid", uuid_)
        L.append("    udp: true"); w("network", "ws")
        L.append("    ws-opts:"); w("path", "/", 6)
    elif proto == "VLESS-WS-CF":
        # CF 隧道节点：server 优先用优选入口，servername/Host 保持隧道域名（CF 靠它路由）
        domain = (n.get("argo_domain") or "").replace("https://", "").rstrip("/")
        if not domain:
            return None  # 域名缺失（隧道未建立）时跳过，避免输出死节点
        server = (n.get("entry") or "").strip() or domain
        L.append(f"  - name: {_y(name)}"); w("type", "vless"); w("server", server)
        L.append("    port: 443")
        w("uuid", uuid_)
        L.append("    udp: true"); L.append("    tls: true"); w("servername", domain)
        w("network", "ws")
        L.append("    ws-opts:"); w("path", "/", 6)
        L.append("      headers:"); w("Host", domain, 8)
    elif proto == "SS-2022":
        L.append(f"  - name: {_y(name)}"); w("type", "ss"); w("server", ip); L.append(f"    port: {port}")
        w("cipher", "2022-blake3-aes-128-gcm"); w("password", pwd); L.append("    udp: true")
    elif proto == "Naive":
        # mihomo 不支持 naive 协议 → 跳过（base64 订阅里仍保留）
        return None
    else:
        return None
    return "\n".join(L) + "\n"


def build_clash_yaml(specs: list[dict], sub_title="NexPanel") -> str:
    proxies, names = [], []
    used = set()
    for i, n in enumerate(specs):
        base = f"{n.get('_app', 'node')}-{n['protocol']}"
        if n.get("_egress"):
            base = f"{base}·{n['_egress']}"
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
# 由 NexPanel 自动生成  ({len(names)} 个节点)
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
        return yaml_text, "text/yaml; charset=utf-8", "attachment; filename=nexpanel-clash.yaml"
    # base64 模式优先用持久化链接（含 naive 等所有协议）
    links = collect_links()
    if not links:
        links = []
    body = base64.b64encode("\n".join(links).encode()).decode()
    return body, "text/plain; charset=utf-8", ""
