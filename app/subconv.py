"""订阅转换引擎（纯标准库，无新依赖）

支持从外部订阅导入节点（机场/其他面板），并互相转换为：
  * Clash.Meta / mihomo YAML 订阅
  * Base64 URI 订阅（v2rayNG / Shadowrocket / NekoBox 等）

输入识别：
  * 明文分享链接（多行 vless:// vmess:// trojan:// ss:// hysteria2:// tuic://...）
  * Base64 包装的分享链接列表（机场常见）
  * Clash YAML（含 proxies 列表，支持 ws/grpc/h2/reality 等传输层）

统一节点模型字段：
  name,type,server,port,uuid,password,cipher,network,tls,sni,host,path,flow,
  pbk,sid,fp,alpn,alterId,skip_cert_verify,obfs,obfs_password,congestion,_src
"""
import base64
import json
import secrets
import time
import urllib.parse as up
import urllib.request as ureq

from . import db

UA = "NexPanel-SubConv/1.0 (ClashMetaForAndroid-compatible)"

# ────────────────────────── 基础工具 ──────────────────────────


def _b64d(s: str) -> bytes:
    s = (s or "").strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        return base64.b64decode(s)
    except Exception:
        return b""


def _b64e(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _unq(s) -> str:
    if s is None:
        return ""
    return up.unquote(str(s))


def _qs(qs: dict, *keys) -> str:
    for k in keys:
        v = qs.get(k)
        if v:
            return _unq(v)
    return ""


def _true(qs: dict, *keys) -> bool:
    for k in keys:
        if k in qs and str(qs[k]).lower() in ("1", "true", "yes"):
            return True
    return False


def _port(v, d=443) -> int:
    try:
        return max(1, min(int(v), 65535))
    except Exception:
        return d


def _clip(s, n=80) -> str:
    s = _unq(s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _y(v) -> str:
    """YAML 双引号安全字符串"""
    s = str("" if v is None else v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


# ────────────────────────── 拉取订阅 ──────────────────────────


def fetch_subscription(url: str, timeout: int = 20) -> tuple[str, str]:
    """下载订阅内容。返回 (text, note)。"""
    req = ureq.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with ureq.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        enc = (r.headers.get("Content-Encoding") or "").lower()
        disp = r.headers.get("Content-Disposition") or ""
    if enc == "gzip" or raw[:2] == b"\x1f\x8b":
        import gzip
        raw = gzip.decompress(raw)
    m = __import__("re").search(r'filename\*?=(?:UTF-8\'\')?"?([\w.\-]+)"?', disp)
    hint = m.group(1) if m else ""
    text = raw.decode("utf-8", errors="replace")
    if __import__("re").search(r"^proxies\s*:", text, __import__("re").M):
        return text, ("clash-yaml" + (" · " + hint if hint else ""))
    body = text.strip()
    if not body:
        raise ValueError("订阅内容为空")
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    joined = "".join(lines)
    dec = _b64d(joined)
    if dec and b"://" in dec[:4096] and not any(l.lower().startswith(
            ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://", "tuic://")) for l in lines):
        text = dec.decode("utf-8", errors="replace")
    return text, hint or ("plain" if lines else "?")


# ────────────────────────── URI 解析 ──────────────────────────


def _host_port(hostport: str) -> tuple[str, int] | None:
    m = __import__("re").match(r"^\[([^\]]+)\]:(\d+)$", hostport)
    if m:
        return m.group(1), _port(m.group(2))
    server, _, port_s = hostport.rpartition(":")
    if not server or not port_s:
        return None
    return server, _port(port_s)


def parse_vmess(uri: str) -> dict | None:
    raw = uri.split("://", 1)[1].rsplit("#", 1)
    name = _unq(raw[1]) if len(raw) > 1 else ""
    try:
        data = json.loads(_b64d(raw[0]) or b"{}")
    except Exception:
        return None
    if not data.get("add") or not data.get("port"):
        return None
    n = {
        "name": _clip(data.get("ps") or name or data["add"] + ":" + str(data["port"])),
        "type": "vmess", "server": data["add"], "port": _port(data.get("port")),
        "uuid": data.get("id") or "", "alterId": int(data.get("aid") or 0),
        "network": data.get("net") or "tcp",
        "tls": str(data.get("tls", "")).lower() == "tls" or str(data.get("scy", "")).lower() == "auto",
        "sni": data.get("sni") or data.get("host") or "", "host": data.get("host") or "",
        "path": data.get("path") or "", "alpn": data.get("alpn") or "",
        "_src": "uri",
    }
    return n


def parse_ss(uri: str) -> dict | None:
    """ss://base64(method:password)@server:port#name  / ss://base64(method:password@server:port)#name"""
    raw = uri.split("://", 1)[1]
    if "#" in raw:
        raw, name = raw.rsplit("#", 1)
    else:
        name = ""
    name = _clip(name)
    # SIP002: base64(method:password)@host:port
    if "@" in raw:
        cred_b64, hostport = raw.rsplit("@", 1)
        hp = _host_port(hostport)
        if not hp:
            return None
        dec = _b64d(cred_b64).decode("utf-8", errors="replace")
        if ":" in dec:
            method, password = dec.split(":", 1)
        else:
            return None
    else:
        dec = _b64d(raw).decode("utf-8", errors="replace")
        if "@" not in dec or ":" not in dec.split("@", 1)[0]:
            return None
        cred, hostport = dec.rsplit("@", 1)
        hp = _host_port(hostport)
        if not hp:
            return None
        method, password = cred.split(":", 1)
    if not method or not password or not hp:
        return None
    return {"name": name or (hp[0] + ":" + str(hp[1])), "type": "ss" if "2022-" not in method else "ss2022",
            "server": hp[0], "port": hp[1], "method": method, "password": password, "_src": "uri"}


def parse_vx(scheme: str, uri: str) -> dict | None:
    """vless/trojan/hysteria2/hy2/tuic 共用：userinfo@host:port?params#name"""
    frag = uri.split("://", 1)[1]
    if "#" not in frag:
        frag += "#"
    main, name = frag.split("#", 1)
    name = _clip(name) or scheme
    userinfo, _, hostport = main.partition("@")
    if not hostport:
        return None
    hp = _host_port(hostport)
    if not hp:
        return None
    q = dict(up.parse_qsl(main.split("@", 1)[-1].split("?", 1)[1]) if "?" in main else [])
    n = {"name": name, "server": hp[0], "port": hp[1], "sni": _qs(q, "sni", "peer"),
         "host": _qs(q, "host"), "path": _qs(q, "path"),
         "fp": _qs(q, "fp", "client-fingerprint"), "flow": _qs(q, "flow"),
         "pbk": _qs(q, "pbk", "publicKey"), "sid": _qs(q, "sid", "shortId"),
         "alpn": _qs(q, "alpn").replace("%2C", ","),
         "skip_cert_verify": _true(q, "allowInsecure", "allow_insecure", "insecure"),
         "_src": "uri"}
    scheme = scheme.lower()
    if scheme in ("vless", "trojan"):
        n["type"] = scheme
        n["uuid"] = _unq(userinfo) if scheme == "vless" else ""
        n["password"] = _unq(userinfo) if scheme == "trojan" else ""
        n["network"] = _qs(q, "type") or "tcp"
        sec = _qs(q, "security")
        n["tls"] = sec in ("tls", "reality", "xtls")
        n["reality"] = sec == "reality"
        n["path"] = n["path"] or (("/" if n["network"] == "ws" else ""))
        if n["network"] == "ws" and not n["host"]:
            n["host"] = n["sni"]
    elif scheme in ("hysteria2", "hy2"):
        n["type"] = "hysteria2"
        n["password"] = _unq(userinfo)
        if _qs(q, "obfs"):
            n["obfs"] = "salamander"
            n["obfs_password"] = _qs(q, "obfs-password")
    elif scheme == "tuic":
        n["type"] = "tuic"
        if ":" in userinfo:
            n["uuid"], n["password"] = _unq(userinfo.split(":", 1)[0]), _unq(userinfo.split(":", 1)[1])
        else:
            n["uuid"], n["password"] = _unq(userinfo), ""
        n["congestion"] = _qs(q, "congestion_control") or "bbr"
        n["alpn"] = n["alpn"] or "h3"
    else:
        return None
    return n


def parse_uri(uri: str) -> dict | None:
    uri = (uri or "").strip()
    if "://" not in uri:
        return None
    scheme = uri.split("://", 1)[0].lower()
    try:
        if scheme == "vmess":
            return parse_vmess(uri)
        if scheme == "ss":
            return parse_ss(uri)
        if scheme in ("vless", "trojan", "hysteria2", "hy2", "tuic"):
            return parse_vx(scheme, uri)
        return None
    except Exception:
        return None


# ────────────────────────── Clash YAML 解析 ──────────────────────────


def _yaml_scalar(s: str):
    s = s.strip()
    if not s:
        return ""
    if s.startswith('"') and s.endswith('"'):
        try:
            return json.loads(s)
        except Exception:
            return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1].replace("''", "'")
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", ""):
        return None
    try:
        return int(s)
    except Exception:
        pass
    try:
        return float(s)
    except Exception:
        return s


def _parse_yaml(text: str):
    """极简 YAML 子集解析：重点支持 proxies 列表/映射/嵌套 map。"""
    lines = []
    for ln in text.splitlines():
        if "\ufeff" in ln:
            ln = ln.lstrip("\ufeff")
        lines.append(ln.rstrip())
    pos = 0

    def peek_indent(idx):
        while idx < len(lines):
            ln = lines[idx]
            if ln.strip() and not ln.lstrip().startswith("#"):
                return len(ln) - len(ln.lstrip(" "))
            idx += 1
        return -1

    def parse_block(indent: int):
        nonlocal pos
        obj = {}
        while pos < len(lines):
            ln = lines[pos]
            if not ln.strip() or ln.lstrip().startswith("#"):
                pos += 1
                continue
            cur = len(ln) - len(ln.lstrip(" "))
            if cur < indent:
                break
            if cur > indent:
                raise ValueError("unexpected indent")
            body = ln.strip()
            if body.startswith("- "):
                # 列表项：- name: xxx，后续同缩进更深的键都归属该项
                rest = body[2:].strip()
                item = {}
                if ":" in rest:
                    k, _, v = rest.partition(":")
                    item[k.strip().strip("'\"")] = _yaml_scalar(v.strip())
                ni = peek_indent(pos + 1)
                if ni > cur:
                    pos += 1
                    child = parse_block(ni)
                    if isinstance(child, dict):
                        for kk, vv in child.items():
                            item[kk] = vv
                else:
                    pos += 1
                obj.setdefault("_list", []).append(item)
            else:
                if ":" not in body:
                    pos += 1
                    continue
                k, _, v = body.partition(":")
                k = k.strip().strip("'\"")
                v = v.strip()
                if not v:
                    ni = peek_indent(pos + 1)
                    if ni > cur:
                        pos += 1
                        obj[k] = parse_block(ni)
                    else:
                        obj[k] = []
                        pos += 1
                else:
                    obj[k] = _yaml_scalar(v)
                    pos += 1
        return obj

    root = parse_block(0)
    if isinstance(root, dict) and len(root) == 1 and "_list" in root:
        return root["_list"]
    return root


def _clash_proxy_to_node(p: dict, src: str = "clash") -> dict | None:
    try:
        typ = str(p.get("type") or "").lower()
        server = str(p.get("server") or "")
        port = _port(p.get("port"))
        if not typ or not server:
            return None
        n = {"name": _clip(p.get("name") or f"{server}:{port}"), "type": typ,
             "server": server, "port": port, "_src": src}
        ws = p.get("ws-opts") or {}
        gr = p.get("grpc-opts") or {}
        h2 = p.get("h2-opts") or {}
        n["network"] = (p.get("network") or ("ws" if ws else "grpc" if gr else "tcp"))
        n["tls"] = bool(p.get("tls"))
        n["sni"] = p.get("servername") or (p.get("sni") or "")
        n["fp"] = p.get("client-fingerprint") or ""
        n["flow"] = p.get("flow") or ""
        n["alpn"] = p.get("alpn") or ""
        n["skip_cert_verify"] = bool(p.get("skip-cert-verify"))
        n["path"] = ws.get("path") or gr.get("grpc-service-name") or h2.get("path") or ""
        host_hdr = ""
        if isinstance(ws.get("headers"), dict):
            host_hdr = ws["headers"].get("Host", "")
        n["host"] = ws.get("host") or host_hdr or (h2.get("host") or "")
        ro = p.get("reality-opts") or {}
        n["reality"] = bool(ro) or bool(p.get("pbk") or p.get("public-key") or "")
        n["pbk"] = ro.get("public-key") or p.get("pbk") or ""
        n["sid"] = ro.get("short-id") or p.get("sid") or ""
        if typ == "vless":
            n["uuid"] = p.get("uuid") or ""
        elif typ == "vmess":
            n["uuid"] = p.get("uuid") or ""
            n["alterId"] = int(p.get("alterId") or 0)
        elif typ == "trojan":
            n["password"] = p.get("password") or ""
        elif typ == "ss":
            n["method"] = p.get("cipher") or "aes-128-gcm"
            n["password"] = p.get("password") or ""
        elif typ == "hysteria2":
            n["password"] = p.get("password") or ""
            n["obfs"] = p.get("obfs") or ""
            if p.get("obfs-password"):
                n["obfs_password"] = p["obfs-password"]
        elif typ == "tuic":
            n["uuid"] = p.get("uuid") or ""
            n["password"] = p.get("password") or ""
            n["congestion"] = p.get("congestion-control") or "bbr"
        else:
            return None
        return n
    except Exception:
        return None


def parse_clash_yaml(text: str) -> list[dict]:
    try:
        root = _parse_yaml(text)
    except Exception:
        return []
    if not isinstance(root, dict):
        return []
    proxies = root.get("proxies") or []
    if isinstance(proxies, dict) and "_list" in proxies:
        proxies = proxies["_list"]
    out = []
    for p in proxies:
        if isinstance(p, dict):
            n = _clash_proxy_to_node(p, "clash")
            if n:
                out.append(n)
    return out


# ────────────────────────── 自动识别并解析订阅文本 ──────────────────────────


def parse_subscription_text(text: str) -> list[dict]:
    text = (text or "").strip()
    if not text:
        return []
    if __import__("re").search(r"^proxies\s*:", text, __import__("re").M):
        return parse_clash_yaml(text)
    # base64 包裹
    joined = "".join(l.strip() for l in text.splitlines() if l.strip())
    dec = _b64d(joined)
    if dec and b"://" in dec[:4096]:
        text = dec.decode("utf-8", errors="replace")
    nodes = []
    seen = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        n = parse_uri(line)
        if not n:
            continue
        key = (n.get("type"), n.get("server"), n.get("port"))
        if key in seen:
            continue
        seen.add(key)
        nodes.append(n)
    return nodes


def parse_url(url: str) -> tuple[list[dict], str]:
    text, note = fetch_subscription(url)
    return parse_subscription_text(text), note


# ────────────────────────── 输出：分享链接 ──────────────────────────


def to_uri(n: dict) -> str | None:
    typ = n.get("type", "").lower()
    server = n.get("server") or ""
    port = n.get("port") or 443
    name = up.quote(_clip(n.get("name") or f"{server}:{port}"))
    try:
        if typ == "vless":
            q = {"encryption": "none"}
            if n.get("flow"):
                q["flow"] = n["flow"]
            if n.get("tls"):
                q["security"] = "reality" if n.get("reality") else "tls"
                if n.get("sni"):
                    q["sni"] = n["sni"]
                if n.get("fp"):
                    q["fp"] = n["fp"]
                if n.get("pbk"):
                    q["pbk"] = n["pbk"]
                if n.get("sid"):
                    q["sid"] = n["sid"]
                if n.get("alpn"):
                    q["alpn"] = n["alpn"]
            q["type"] = n.get("network") or "tcp"
            if q["type"] in ("ws", "h2"):
                if n.get("path"):
                    q["path"] = n["path"]
                if n.get("host"):
                    q["host"] = n["host"]
            return f"vless://{n.get('uuid')}@{server}:{port}?" + up.urlencode(q) + "#" + name
        if typ == "vmess":
            data = {
                "v": "2", "ps": n.get("name") or "", "add": server, "port": str(port),
                "id": n.get("uuid") or "", "aid": str(n.get("alterId") or 0),
                "net": n.get("network") or "tcp", "type": "none",
                "host": n.get("host") or "", "path": n.get("path") or "",
                "tls": "tls" if n.get("tls") else "", "sni": n.get("sni") or "",
            }
            return "vmess://" + _b64e(json.dumps(data, separators=(",", ":")))
        if typ == "trojan":
            q = {}
            if n.get("sni"):
                q["sni"] = n["sni"]
            if (n.get("network") or "") in ("ws", "grpc", "h2"):
                q["type"] = n["network"]
                if n.get("path"):
                    q["path"] = n["path"]
                if n.get("host"):
                    q["host"] = n["host"]
            return f"trojan://{up.quote(n.get('password') or '')}@{server}:{port}?" + up.urlencode(q) + "#" + name
        if typ in ("ss", "ss2022"):
            cred = _b64e(f"{n.get('method') or 'aes-128-gcm'}:{n.get('password') or ''}")
            return f"ss://{cred}@{server}:{port}#" + name
        if typ == "hysteria2":
            q = {}
            if n.get("sni"):
                q["sni"] = n["sni"]
            if n.get("skip_cert_verify"):
                q["insecure"] = "1"
            if n.get("obfs"):
                q["obfs"] = n["obfs"]
            if n.get("obfs_password"):
                q["obfs-password"] = n["obfs_password"]
            return f"hysteria2://{up.quote(n.get('password') or '')}@{server}:{port}?" + up.urlencode(q) + "#" + name
        if typ == "tuic":
            q = {}
            if n.get("sni"):
                q["sni"] = n["sni"]
            if n.get("alpn"):
                q["alpn"] = n["alpn"]
            if n.get("congestion"):
                q["congestion_control"] = n["congestion"]
            uid = n.get("uuid") or ""
            pwd = n.get("password") or ""
            user = up.quote(f"{uid}:{pwd}")
            return f"tuic://{user}@{server}:{port}?" + up.urlencode(q) + "#" + name
    except Exception:
        return None
    return None


# ────────────────────────── 输出：Clash YAML proxy 片段 ──────────────────────────


def _clash_proxy_block(n: dict) -> str | None:
    L = []

    def w(k, val, indent=4):
        L.append(" " * indent + f"{k}: {_y(val)}")

    def wl(k, *vals, indent=4):
        L.append(" " * indent + f"{k}:")
        for x in vals:
            L.append(" " * (indent + 2) + f"- {_y(x)}")

    def wraw(k, val, indent=4):
        L.append(" " * indent + f"{k}: {val}")

    typ = n.get("type")
    name = n.get("name") or f"{n.get('server')}:{n.get('port')}"
    server = n.get("server") or ""
    port = int(n.get("port") or 443)
    net = n.get("network") or "tcp"
    L.append(f"  - name: {_y(name)}")
    w("type", typ); w("server", server); wraw("port", port); wraw("udp", "true")
    if typ == "vless":
        w("uuid", n.get("uuid") or "")
        if n.get("flow"):
            w("flow", n["flow"])
    elif typ == "vmess":
        w("uuid", n.get("uuid") or "")
        w("alterId", str(n.get("alterId") or 0))
    elif typ == "trojan":
        w("password", n.get("password") or "")
    elif typ == "ss":
        w("cipher", n.get("method") or "aes-128-gcm")
        w("password", n.get("password") or "")
    elif typ == "hysteria2":
        w("password", n.get("password") or "")
        if n.get("obfs"):
            w("obfs", n["obfs"])
            if n.get("obfs_password"):
                w("obfs-password", n["obfs_password"])
    elif typ == "tuic":
        w("uuid", n.get("uuid") or "")
        w("password", n.get("password") or "")
        w("congestion-control", n.get("congestion") or "bbr")
        if n.get("alpn"):
            w("alpn", n["alpn"])
    else:
        return None
    if n.get("tls") or typ == "vless":
        if typ in ("vless", "vmess"):
            wraw("tls", "true")
            if n.get("sni"):
                w("servername", n["sni"])
            if n.get("fp"):
                w("client-fingerprint", n["fp"])
            if n.get("alpn"):
                w("alpn", n["alpn"])
    if n.get("skip_cert_verify"):
        wraw("skip-cert-verify", "true")
    if typ in ("vless", "vmess", "trojan"):
        if net == "ws":
            w("network", "ws")
            L.append("    ws-opts:")
            if n.get("path"):
                w("path", n["path"], 6)
            if n.get("host"):
                L.append(" " * 6 + "headers:")
                L.append(" " * 8 + f"Host: {_y(n['host'])}")
        elif net == "grpc":
            w("network", "grpc")
            L.append("    grpc-opts:")
            if n.get("path"):
                w("grpc-service-name", n["path"], 6)
        elif net == "h2":
            w("network", "h2")
            L.append("    h2-opts:")
            if n.get("path"):
                w("path", n["path"], 6)
            if n.get("host"):
                w("host", n["host"], 6)
    if n.get("reality") and n.get("pbk"):
        L.append("    reality-opts:")
        w("public-key", n.get("pbk") or "", 6)
        w("short-id", n.get("sid") or "", 6)
    return "\n".join(L) + "\n"


def build_clash_yaml(nodes: list[dict], title: str = "NexPanel 转换") -> str:
    proxies = []
    names = []
    used = set()
    for n in nodes:
        base = n.get("name") or f"{n.get('server')}:{n.get('port')}"
        nm, k = base, 2
        while nm in used:
            nm, k = f"{base}#{k}", k + 1
        used.add(nm)
        nn = dict(n)
        nn["name"] = nm
        block = _clash_proxy_block(nn)
        if block:
            proxies.append(block.rstrip("\n"))
            names.append(nm)
    names_yaml = "\n".join(f"      - {_y(x)}" for x in names) if names else "      - DIRECT"
    return f"""# {title} · Clash.Meta / mihomo
# 由 NexPanel 订阅转换生成  ({len(names)} 个节点)
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


def build_base64_uri(nodes: list[dict]) -> str:
    uris = []
    for n in nodes:
        u = to_uri(n)
        if u:
            uris.append(u)
    return _b64e("\n".join(uris))


# ────────────────────────── 持久化：subconv 表 ──────────────────────────


def ensure_table():
    db.ex("""CREATE TABLE IF NOT EXISTS subconv(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        token TEXT NOT NULL UNIQUE,
        url TEXT DEFAULT '',
        content TEXT DEFAULT '',
        nodes TEXT DEFAULT '[]',
        note TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    )""")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _load_nodes(row) -> list[dict]:
    try:
        return json.loads(row["nodes"] or "[]")
    except Exception:
        return []


def list_sources():
    ensure_table()
    rows = db.q("SELECT * FROM subconv ORDER BY id DESC")
    out = []
    for r in rows:
        d = dict(r)
        d["nodes"] = _load_nodes(r)
        d["node_count"] = len(d["nodes"])
        d.pop("content", None)
        out.append(d)
    return out


def get_source_by_token(token: str):
    ensure_table()
    row = db.one("SELECT * FROM subconv WHERE token=?", (token,))
    return row


def add_source(name: str, url: str = "", content: str = "") -> dict:
    ensure_table()
    name = name or "未命名订阅"
    token = secrets.token_urlsafe(16)
    err = ""
    nodes: list[dict] = []
    note = ""
    try:
        if url:
            nodes, note = parse_url(url)
        elif content:
            nodes = parse_subscription_text(content)
            note = "content"
        if not nodes:
            err = "未解析到任何节点（协议可能不支持或订阅为空）"
    except Exception as e:
        err = f"拉取/解析失败: {e}"
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    now = _now()
    db.ex("""INSERT INTO subconv(name,token,url,content,nodes,note,created_at,updated_at)
             VALUES(?,?,?,?,?,?,?,?)""",
          (name, token, url, content, nodes_json, note, now, now))
    row = db.one("SELECT * FROM subconv WHERE token=?", (token,))
    d = dict(row)
    d["nodes"] = nodes
    d["node_count"] = len(nodes)
    d["error"] = err
    return d


def refresh_source(sid: int) -> dict:
    ensure_table()
    row = db.one("SELECT * FROM subconv WHERE id=?", (sid,))
    if not row:
        raise KeyError("订阅不存在")
    nodes: list[dict] = []
    note, err = "", ""
    try:
        if row["url"]:
            nodes, note = parse_url(row["url"])
        elif row["content"]:
            nodes = parse_subscription_text(row["content"])
            note = "content"
        if not nodes:
            err = "未解析到任何节点"
    except Exception as e:
        err = f"拉取/解析失败: {e}"
    db.ex("UPDATE subconv SET nodes=?, note=?, updated_at=? WHERE id=?",
          (json.dumps(nodes, ensure_ascii=False), note, _now(), sid))
    out = dict(db.one("SELECT * FROM subconv WHERE id=?", (sid,)))
    out["nodes"] = nodes
    out["node_count"] = len(nodes)
    out["error"] = err
    return out


def delete_source(sid: int):
    ensure_table()
    db.ex("DELETE FROM subconv WHERE id=?", (sid,))


def node_uris(sid_or_token, by_token=False):
    ensure_table()
    if by_token:
        row = db.one("SELECT * FROM subconv WHERE token=?", (sid_or_token,))
    else:
        row = db.one("SELECT * FROM subconv WHERE id=?", (sid_or_token,))
    if not row:
        return []
    return _load_nodes(row)
