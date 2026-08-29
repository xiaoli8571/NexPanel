"""应用出口（egress）：WARP IPv4/IPv6/双栈 + 住宅代理（SOCKS5/HTTP）

概念移植自 X-UI-Server 的 egress_mode（native/residential/warp_ipv4/warp_ipv6/warp_dual/socks5），
落地方式适配 NexPanel 架构：sing-box 1.12.x 运行在 LXC 容器内，出站直接在
sing-box 配置层注入（WARP = wireguard endpoint，住宅 = socks5/http outbound），
无需在节点系统层安装任何内核模块或 TUN 设备。

数据存储：apps.params JSON 的 "egress" 字段 + "egress_state"（应用状态机）。
WARP 注册凭据缓存于 settings 表（key = warp_reg:<app_id>），删除出口时清理。
"""
import base64
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey)

from . import db

VALID_MODES = ["native", "residential", "warp_ipv4", "warp_ipv6", "warp_dual"]

WARP_API = "https://api.cloudflareclient.com/v0a2158/reg"
WARP_PEER_PUB = "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="  # WARP 固定对端公钥
WARP_HOST = "engage.cloudflareclient.com"
WARP_PORT = 2408

MODE_LABELS = {
    "native": "原生出口", "residential": "住宅代理",
    "warp_ipv4": "WARP IPv4", "warp_ipv6": "WARP IPv6", "warp_dual": "WARP 双栈",
}


# ────────────── WARP 账号注册（wgcf 同款流程，纯 HTTP 无依赖） ──────────────

def _gen_keypair() -> tuple[str, str]:
    """返回 (private_key_b64, public_key_b64) —— WireGuard 标准字母表 base64"""
    priv = X25519PrivateKey.generate()
    raw_priv = priv.private_bytes_raw()
    raw_pub = priv.public_key().public_bytes_raw()
    b64 = lambda b: base64.b64encode(b).decode()
    return b64(raw_priv), b64(raw_pub)


def _warp_register() -> dict:
    """注册一台新的 WARP 设备，返回精简凭据 dict"""
    priv_b64, pub_b64 = _gen_keypair()
    body = json.dumps({
        "key": pub_b64, "install_id": "", "fcm_token": "",
        "tos": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "model": "PC", "locale": "en_US", "warp_enabled": True,
    }).encode()
    req = urllib.request.Request(
        WARP_API, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "okhttp/3.12.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    iface = (data.get("config") or {}).get("interface") or {}
    addrs = iface.get("addresses") or {}
    peers = (data.get("config") or {}).get("peers") or []
    peer_pub = (peers[0].get("public_key") if peers else "") or \
               iface.get("peer_public_key") or WARP_PEER_PUB
    if not addrs.get("v4") and not addrs.get("v6"):
        raise RuntimeError(f"WARP 注册响应缺少地址: {str(data)[:200]}")
    return {
        "private_key": priv_b64,
        "peer_public_key": peer_pub,
        "v4": (addrs.get("v4") or "").strip(),
        "v6": (addrs.get("v6") or "").strip(),
        "account_id": data.get("id", ""),
        "registered_at": int(time.time()),
    }


def warp_reg_for(app_id: int) -> dict:
    """取该应用的 WARP 凭据（settings 缓存，首次注册）"""
    key = f"warp_reg:{app_id}"
    row = db.one("SELECT value FROM settings WHERE key=?", (key,))
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            pass
    reg = _warp_register()
    db.ex("INSERT INTO settings(key,value) VALUES(?,?) "
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
          (key, json.dumps(reg)))
    return reg


def warp_drop(app_id: int):
    db.ex("DELETE FROM settings WHERE key=?", (f"warp_reg:{app_id}",))


# ────────────── sing-box 配置注入（1.12.x schema） ──────────────

def _warp_endpoint(reg: dict, mode: str) -> dict:
    """按模式生成 wireguard endpoint：ipv4 只配 v4 地址，ipv6 只配 v6，dual 两个都配"""
    address = []
    if mode in ("warp_ipv4", "warp_dual") and reg.get("v4"):
        address.append(f"{reg['v4']}/32")
    if mode in ("warp_ipv6", "warp_dual") and reg.get("v6"):
        address.append(f"{reg['v6']}/128")
    if not address:
        raise RuntimeError(f"WARP 凭据缺少 {mode} 所需地址")
    return {
        "type": "wireguard", "tag": "warp-out", "address": address,
        "private_key": reg["private_key"], "mtu": 1280,
        "peers": [{"public_key": reg.get("peer_public_key") or WARP_PEER_PUB,
                   "address": WARP_HOST, "port": WARP_PORT,
                   "allowed_ips": ["0.0.0.0/0", "::/0"]}],
    }


def _resi_outbound(egress: dict) -> dict:
    proto = egress.get("resi_proto") or "socks5"
    ob = {"type": "socks" if proto == "socks5" else "http",
          "tag": "resi-out",
          "server": egress.get("resi_addr", ""),
          "server_port": int(egress.get("resi_port") or 0)}
    if egress.get("resi_user"):
        ob["username"] = egress["resi_user"]
        ob["password"] = egress.get("resi_pass", "")
    if egress.get("resi_tls"):
        ob["tls"] = {"enabled": True,
                     "insecure": bool(egress.get("resi_tls_insecure"))}
    return ob


def _selective_domains(egress: dict) -> list[str]:
    raw = egress.get("resi_domains") or ""
    return [d.strip().lstrip(".").lower() for d in re.split(r"[,\n\s]+", raw)
            if d.strip()]


def apply_egress(conf: dict, egress: dict | None, app_id: int,
                 resi_gw: str | None = None) -> tuple[dict, str]:
    """把 egress 配置注入 sing-box conf（原地修改并返回），返回 (conf, 说明)

    - global:  route.final = 出站（全部流量走出口）
    - selective: 仅 domain_suffix 命中的目标走出口，其余保持默认直连
    - resi_gw: 住宅出口网关（宿主网桥 IP；宿主直装传 None → 127.0.0.1）
    """
    mode = (egress or {}).get("mode", "native")
    if mode == "native" or not egress:
        return conf, "原生出口"

    conf.setdefault("route", {}).setdefault("rules", [])

    if mode.startswith("warp_"):
        reg = warp_reg_for(app_id)
        endpoint = _warp_endpoint(reg, mode)
        conf.setdefault("endpoints", []).append(endpoint)
        tag, note = "warp-out", f"{MODE_LABELS[mode]}（WARP 端点 {WARP_HOST}:{WARP_PORT}）"
    elif mode == "residential":
        if egress.get("country"):                     # 新格式：VPN Gate 节点级住宅出口
            cc = egress["country"].upper()
            gw = resi_gw or "127.0.0.1"
            ob = {"type": "socks", "tag": "resi-out", "server": gw, "server_port": 7920}
            conf.setdefault("outbounds", []).append(ob)
            tag, note = "resi-out", f"住宅出口·{cc}（VPN Gate 经宿主 {gw}:7920）"
        else:                                          # 旧格式：自定义上游代理
            if not egress.get("resi_addr") or not egress.get("resi_port"):
                raise ValueError("住宅代理需要填写地址和端口")
            ob = _resi_outbound(egress)
            conf.setdefault("outbounds", []).append(ob)
            tag, note = "resi-out", (f"住宅代理（{ob['type']}://{ob['server']}:{ob['server_port']}）")
    else:
        raise ValueError(f"未知出口模式: {mode}")

    if egress.get("resi_mode") == "selective":
        domains = _selective_domains(egress)
        if not domains:
            raise ValueError("分流模式需要填写域名后缀列表")
        conf["route"]["rules"] = [
            {"domain_suffix": domains, "outbound": tag}
        ] + conf["route"]["rules"]
        note += f" · 分流 {len(domains)} 个域名后缀"
    else:
        conf["route"]["final"] = tag
        note += " · 全局接管"
    return conf, note


# ────────────── 输入清洗与状态 ──────────────

def normalize(payload: dict) -> dict:
    """校验并清洗前端提交的 egress 配置"""
    mode = (payload.get("mode") or "native").strip()
    if mode not in VALID_MODES:
        raise ValueError(f"无效出口模式: {mode}")
    e: dict = {"mode": mode}
    if mode == "residential":
        resi_mode = payload.get("resi_mode") or "global"
        if resi_mode not in ("global", "selective"):
            raise ValueError("分流模式无效")
        country = (payload.get("country") or "").strip().upper()
        if country:                                  # 新格式：VPN Gate 选国家
            if not re.fullmatch(r"[A-Z]{2}", country):
                raise ValueError("国家代码无效（两位字母，如 JP / US / SG）")
            e.update({"country": country, "resi_mode": resi_mode,
                      "resi_domains": (payload.get("resi_domains") or "")[:2048]})
        else:                                        # 旧格式：自定义上游
            proto = payload.get("resi_proto") or "socks5"
            if proto not in ("socks5", "http"):
                raise ValueError("住宅代理协议仅支持 socks5 / http")
            addr = (payload.get("resi_addr") or "").strip()
            port = int(payload.get("resi_port") or 0)
            if not addr or not (1 <= port <= 65535):
                raise ValueError("住宅代理地址/端口无效（或填写国家代码）")
            e.update({
                "resi_proto": proto, "resi_addr": addr[:128],
                "resi_port": port,
                "resi_user": (payload.get("resi_user") or "")[:64],
                "resi_pass": (payload.get("resi_pass") or "")[:128],
                "resi_mode": resi_mode,
                "resi_domains": (payload.get("resi_domains") or "")[:2048],
            })
        if resi_mode == "selective" and not _selective_domains(e):
            raise ValueError("分流模式需要填写至少一个域名后缀（如 openai.com）")
    return e


def machine_egress(container_id: int | None, node_id: int,
                   exclude_app_id: int | None = None) -> tuple[dict | None, int | None]:
    """同一台机器上所有应用中生效的出口（第一个非 native 的 app 优先，id 小者优先）"""
    if container_id is not None:
        rows = db.q("SELECT id, params FROM apps WHERE status='done' AND container_id=? "
                    "AND (? IS NULL OR id != ?) ORDER BY id",
                    container_id, exclude_app_id, exclude_app_id)
    else:
        rows = db.q("SELECT id, params FROM apps WHERE status='done' AND container_id IS NULL "
                    "AND (node_id=? OR (node_id IS NULL AND name=(SELECT name FROM nodes WHERE id=?))) "
                    "AND (? IS NULL OR id != ?) ORDER BY id",
                    node_id, node_id, exclude_app_id, exclude_app_id)
    for r in rows:
        try:
            params = json.loads(r["params"] or "{}")
        except Exception:
            continue
        eg = params.get("egress") or {}
        if eg.get("mode") not in (None, "", "native"):
            return eg, r["id"]
    return None, None
