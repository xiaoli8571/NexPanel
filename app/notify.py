"""Telegram 告警通知模块

通过 Bot API 发送告警消息。
配置存储在 settings 表中：
- notify_telegram_bot_token: Bot Token
- notify_telegram_chat_id: 目标 Chat ID（群组或用户）
- notify_enabled: "1" / "0"
- notify_events: 逗号分隔的事件列表
"""
import asyncio
import json
import time
from typing import Any

from . import db

# ── 事件类型 ──
EVENTS = {
    "node_offline": "节点离线告警",
    "node_online": "节点上线通知",
    "container_crash": "容器异常告警",
    "backup_fail": "备份失败告警",
    "backup_success": "备份成功通知",
    "system_error": "系统错误告警",
    "traffic_limit": "流量超限告警",
    "disk_full": "磁盘空间不足告警",
}


def get_settings() -> dict:
    """获取当前通知配置"""
    bot_token = db.one("SELECT value FROM settings WHERE key='notify_telegram_bot_token'")
    chat_id = db.one("SELECT value FROM settings WHERE key='notify_telegram_chat_id'")
    enabled = db.one("SELECT value FROM settings WHERE key='notify_enabled'")
    events = db.one("SELECT value FROM settings WHERE key='notify_events'")
    return {
        "bot_token": (bot_token["value"] if bot_token else ""),
        "chat_id": (chat_id["value"] if chat_id else ""),
        "enabled": (enabled["value"] if enabled else "0") == "1",
        "events": (events["value"] if events else "node_offline,container_crash"),
    }


def save_settings(bot_token: str, chat_id: str, enabled: bool, events: str):
    """保存通知配置"""
    db.ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
          "notify_telegram_bot_token", bot_token)
    db.ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
          "notify_telegram_chat_id", chat_id)
    db.ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
          "notify_enabled", "1" if enabled else "0")
    db.ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
          "notify_events", events)


def _http_post(url: str, data: dict, timeout: int = 10) -> str | None:
    """同步 POST 请求（纯标准库，无需 aiohttp）"""
    import urllib.request
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode()
    except Exception as e:
        return None


def send_telegram(text: str, parse_mode: str = "HTML") -> bool:
    """发送 Telegram 消息，返回是否成功"""
    cfg = get_settings()
    if not cfg["enabled"] or not cfg["bot_token"] or not cfg["chat_id"]:
        return False
    api_url = f"https://api.telegram.org/bot{cfg['bot_token']}/sendMessage"
    resp = _http_post(api_url, {
        "chat_id": cfg["chat_id"],
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    })
    if resp is None:
        print("[notify] Telegram 发送失败", flush=True)
        return False
    try:
        data = json.loads(resp)
        if not data.get("ok"):
            print(f"[notify] Telegram 返回错误: {resp[:200]}", flush=True)
            return False
        return True
    except Exception:
        return False


def notify(event: str, title: str, message: str, detail: str = "") -> bool:
    """发送事件通知（检查事件是否在启用的列表中）"""
    cfg = get_settings()
    if not cfg["enabled"]:
        return False
    allowed = [e.strip() for e in cfg["events"].split(",") if e.strip()]
    if event not in allowed and "all" not in allowed:
        return False

    text = (
        f"<b>🔔 {title}</b>\n"
        f"<pre>{message}</pre>\n"
        f"<i>{db.now()} | NexPanel</i>"
    )
    if detail:
        text += f"\n<code>{detail[:500]}</code>"

    ok = send_telegram(text)
    if ok:
        print(f"[notify] {event} 告警已发送: {title}", flush=True)
    return ok