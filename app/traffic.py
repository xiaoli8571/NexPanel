"""节点流量统计 + 订阅限额模块

功能：
1. 节点流量统计：记录节点各网卡流量，按天/月汇总
2. 订阅限额：基于应用的订阅限流（目前为记录，后续可实现主动限速）

数据表：
- traffic_log: 流量日志表
- subscription_limits: 订阅限额配置

流量数据来源：
- SSH 节点：采集脚本返回的 NET 行（rx/tx bytes）
- Agent 节点：心跳报告中的 rx_kbps/tx_kbps
"""
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from . import db, monitor

# ── 新表创建 ──
TRAFFIC_TABLES = """
CREATE TABLE IF NOT EXISTS traffic_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL,
    rx_bytes INTEGER DEFAULT 0,
    tx_bytes INTEGER DEFAULT 0,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traffic_node_date ON traffic_log(node_id, recorded_at);

CREATE TABLE IF NOT EXISTS traffic_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    rx_bytes INTEGER DEFAULT 0,
    tx_bytes INTEGER DEFAULT 0,
    UNIQUE(node_id, date)
);
CREATE INDEX IF NOT EXISTS idx_traffic_daily_node ON traffic_daily(node_id, date);

CREATE TABLE IF NOT EXISTS subscription_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER NOT NULL,
    traffic_limit_mb INTEGER DEFAULT 0,        -- 流量限额 (MB)，0=不限
    bandwidth_limit_kbps INTEGER DEFAULT 0,     -- 带宽限额 (Kbps)，0=不限
    expire_at TEXT DEFAULT '',                   -- 过期时间
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sub_limits_app ON subscription_limits(app_id);

-- apps 表增加流量使用字段（如果不存在）
"""
# apps 表字段变更通过迁移脚本处理

# ── 缓存 ──
_prev_traffic: dict[int, dict] = {}  # node_id -> {"rx": int, "tx": int, "ts": float}


def init_tables():
    """初始化流量统计相关表"""
    _conn = db._conn
    if not _conn:
        return
    _conn.executescript(TRAFFIC_TABLES)
    _conn.commit()

    # 迁移：apps 表增加流量字段
    try:
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(apps)")]
        if "traffic_rx_bytes" not in cols:
            _conn.execute("ALTER TABLE apps ADD COLUMN traffic_rx_bytes INTEGER DEFAULT 0")
        if "traffic_tx_bytes" not in cols:
            _conn.execute("ALTER TABLE apps ADD COLUMN traffic_tx_bytes INTEGER DEFAULT 0")
        if "traffic_reset_at" not in cols:
            _conn.execute("ALTER TABLE apps ADD COLUMN traffic_reset_at TEXT DEFAULT ''")
        _conn.commit()
    except Exception:
        pass


def record_traffic(node_id: int, rx_kbps: float, tx_kbps: float):
    """记录节点流量（用于后台采集）"""
    now = db.now()
    today = now[:10]  # YYYY-MM-DD

    # 转换为 bytes (kbps * 秒)
    rx_bytes = int(rx_kbps * 1000 / 8)
    tx_bytes = int(tx_kbps * 1000 / 8)

    if rx_bytes <= 0 and tx_bytes <= 0:
        return

    # 记录到 traffic_log
    db.ex("INSERT INTO traffic_log(node_id, rx_bytes, tx_bytes, recorded_at) VALUES(?,?,?,?)",
          node_id, rx_bytes, tx_bytes, now)

    # 汇总到 daily
    db.ex("INSERT INTO traffic_daily(node_id, date, rx_bytes, tx_bytes) VALUES(?,?,?,?) "
          "ON CONFLICT(node_id, date) DO UPDATE SET "
          "rx_bytes = rx_bytes + excluded.rx_bytes, "
          "tx_bytes = tx_bytes + excluded.tx_bytes",
          node_id, today, rx_bytes, tx_bytes)


# ── 批量累计：Agent 心跳很密集（终端会话期间一秒好几次），逐条落库会把
#    事件循环钉在 SQLite 提交上（终端回显因此被拖慢）。这里按节点在内存里累计，
#    每 FLUSH_S 秒合并成一笔写库，总量不变但写次数下降一个数量级。
FLUSH_S = 30.0
_pending: dict[int, dict] = {}          # node_id -> {"rx":bytes,"tx":bytes,"date":..}
_flush_t: dict[int, float] = {}         # node_id -> 上次落库时间
_last_s: dict[int, float] = {}          # node_id -> 上次采样时间(算 dt 用)
_pending_lock = threading.Lock()


def accumulate_traffic(node_id: int, rx_kbps: float, tx_kbps: float, dt: float | None = None):
    """按「速率 × 距上次采样的秒数」在内存累计，到达合并窗口再一笔写库。

    dt 缺省取本节点自上次采样以来的真实间隔——这样无论 Agent 轮询快慢，
    累计量都对得上（原来固定「每次采样=1 秒」，轮询周期一变统计就漂）。"""
    now = time.time()
    with _pending_lock:
        prev = _last_s.get(node_id)
        _last_s[node_id] = now
        span = dt if (dt and dt > 0) else ((now - prev) if prev else 0.0)
        span = max(min(span, 300.0), 0.0)
        p = _pending.setdefault(node_id, {"rx": 0, "tx": 0, "date": db.now()[:10]})
        p["rx"] += int(max(rx_kbps, 0) * 1000 / 8 * span)
        p["tx"] += int(max(tx_kbps, 0) * 1000 / 8 * span)
        if now - _flush_t.get(node_id, 0.0) < FLUSH_S:
            return                       # 还没到合并窗口，继续在内存攒
        _flush_t[node_id] = now
        rx_b, tx_b, day = p["rx"], p["tx"], p["date"]
        _pending.pop(node_id, None)
    _write(node_id, rx_b, tx_b, day)


def _write(node_id: int, rx_b: int, tx_b: int, day: str):
    if rx_b <= 0 and tx_b <= 0:
        return
    try:
        db.ex("INSERT INTO traffic_log(node_id, rx_bytes, tx_bytes, recorded_at) VALUES(?,?,?,?)",
              node_id, rx_b, tx_b, db.now())
        db.ex("INSERT INTO traffic_daily(node_id, date, rx_bytes, tx_bytes) VALUES(?,?,?,?) "
              "ON CONFLICT(node_id, date) DO UPDATE SET "
              "rx_bytes = rx_bytes + excluded.rx_bytes, "
              "tx_bytes = tx_bytes + excluded.tx_bytes",
              node_id, day, rx_b, tx_b)
    except Exception:
        pass


def flush_all():
    """退出/定时收尾：把内存里未到合并窗口的流量写库"""
    with _pending_lock:
        items = list(_pending.items())
        _pending.clear()
    for node_id, p in items:
        _write(node_id, p["rx"], p["tx"], p["date"])


def get_node_traffic(node_id: int, days: int = 30) -> dict:
    """获取指定节点的流量统计"""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = db.q(
        "SELECT date, SUM(rx_bytes) as rx, SUM(tx_bytes) as tx "
        "FROM traffic_daily WHERE node_id=? AND date>=? GROUP BY date ORDER BY date",
        node_id, since)
    total_rx = sum(r["rx"] for r in rows)
    total_tx = sum(r["tx"] for r in rows)
    return {
        "node_id": node_id,
        "days": days,
        "total_rx_mb": round(total_rx / 1048576, 2),
        "total_tx_mb": round(total_tx / 1048576, 2),
        "total_mb": round((total_rx + total_tx) / 1048576, 2),
        "daily": [{"date": r["date"],
                   "rx_mb": round(r["rx"] / 1048576, 2),
                   "tx_mb": round(r["tx"] / 1048576, 2)}
                  for r in rows],
    }


def get_all_traffic(days: int = 30) -> list:
    """获取所有节点的流量汇总"""
    result = []
    for row in db.q("SELECT id, name FROM nodes ORDER BY id"):
        stats = get_node_traffic(row["id"], days)
        stats["name"] = row["name"]
        result.append(stats)
    return result


# ── 订阅限额 ──

def get_subscription_limit(app_id: int) -> dict:
    """获取应用的订阅限额配置"""
    row = db.one("SELECT * FROM subscription_limits WHERE app_id=?", (app_id,))
    if not row:
        return {
            "app_id": app_id,
            "traffic_limit_mb": 0,
            "bandwidth_limit_kbps": 0,
            "expire_at": "",
            "notes": "",
        }
    return dict(row)


def set_subscription_limit(app_id: int, traffic_limit_mb: int = 0,
                           bandwidth_limit_kbps: int = 0,
                           expire_at: str = "",
                           notes: str = "") -> dict:
    """设置应用的订阅限额"""
    db.ex("INSERT INTO subscription_limits(app_id, traffic_limit_mb, bandwidth_limit_kbps, expire_at, notes, created_at) "
          "VALUES(?,?,?,?,?,?) ON CONFLICT(app_id) DO UPDATE SET "
          "traffic_limit_mb=excluded.traffic_limit_mb, "
          "bandwidth_limit_kbps=excluded.bandwidth_limit_kbps, "
          "expire_at=excluded.expire_at, "
          "notes=excluded.notes",
          app_id, traffic_limit_mb, bandwidth_limit_kbps, expire_at, notes, db.now())
    return get_subscription_limit(app_id)


def check_subscription_status(app_id: int) -> dict:
    """检查订阅状态：是否超限、是否过期等"""
    limit = get_subscription_limit(app_id)
    if limit["traffic_limit_mb"] <= 0 and limit["bandwidth_limit_kbps"] <= 0 and not limit["expire_at"]:
        return {"ok": True, "reason": "无限制"}

    app = db.one("SELECT traffic_rx_bytes, traffic_tx_bytes, traffic_reset_at FROM apps WHERE id=?", (app_id,))
    if not app:
        return {"ok": False, "reason": "应用不存在"}

    now = datetime.now()
    warnings = []

    # 检查流量
    if limit["traffic_limit_mb"] > 0:
        used_mb = (app["traffic_rx_bytes"] + app["traffic_tx_bytes"]) / 1048576
        if used_mb >= limit["traffic_limit_mb"]:
            return {"ok": False, "reason": f"流量已超限: {used_mb:.0f}/{limit['traffic_limit_mb']} MB"}
        if used_mb > limit["traffic_limit_mb"] * 0.8:
            warnings.append(f"流量即将超限: {used_mb:.0f}/{limit['traffic_limit_mb']} MB")

    # 检查过期
    if limit["expire_at"]:
        try:
            expire = datetime.strptime(limit["expire_at"], "%Y-%m-%d %H:%M:%S")
            if now > expire:
                return {"ok": False, "reason": f"订阅已过期: {limit['expire_at']}"}
            if expire - now < timedelta(days=3):
                warnings.append(f"订阅即将于 {limit['expire_at']} 过期")
        except ValueError:
            pass

    return {"ok": True, "warnings": warnings, "reason": "正常"}


def aggregate_app_traffic(app_id: int, container_ids: list[int] = None) -> dict:
    """汇总应用关联容器的流量（待精细化实现）"""
    # 简单版本：从 apps 表直接读取累计流量
    app = db.one("SELECT traffic_rx_bytes, traffic_tx_bytes, traffic_reset_at FROM apps WHERE id=?", (app_id,))
    if not app:
        return {"rx_mb": 0, "tx_mb": 0, "total_mb": 0}
    rx_mb = app["traffic_rx_bytes"] / 1048576 if app["traffic_rx_bytes"] else 0
    tx_mb = app["traffic_tx_bytes"] / 1048576 if app["traffic_tx_bytes"] else 0
    return {
        "rx_mb": round(rx_mb, 2),
        "tx_mb": round(tx_mb, 2),
        "total_mb": round(rx_mb + tx_mb, 2),
        "reset_at": app["traffic_reset_at"] or "",
    }


def update_app_traffic(app_id: int, rx_bytes: int, tx_bytes: int):
    """更新应用的流量计数器"""
    db.ex("UPDATE apps SET traffic_rx_bytes = traffic_rx_bytes + ?, "
          "traffic_tx_bytes = traffic_tx_bytes + ? WHERE id=?",
          rx_bytes, tx_bytes, app_id)


# ── 后台流量采集集成 ──

def integrate_with_monitor():
    """在监控数据到达时记录流量"""
    # 这个函数会被 monitor.py 中的采集回调调用
    pass


def collect_and_record():
    """遍历所有节点，检查缓存中的流量数据并写入流量表"""
    for node_id, entry in list(monitor.CACHE.items()):
        if not entry or entry.get("status") != "online":
            continue
        host = entry.get("host")
        if not host:
            continue
        rx = host.get("rx_kbps", 0)
        tx = host.get("tx_kbps", 0)
        if rx > 0 or tx > 0:
            record_traffic(node_id, rx, tx)


# 暴露到 notifications 的检查
def check_disk_full() -> list:
    """检查磁盘空间，返回告警列表"""
    warnings = []
    for node_id, entry in list(monitor.CACHE.items()):
        if not entry or entry.get("status") != "online":
            continue
        host = entry.get("host")
        if not host:
            continue
        disk_total = host.get("disk_total_gb", 0)
        disk_used = host.get("disk_used_gb", 0)
        if disk_total > 0:
            pct = disk_used / disk_total * 100
            if pct > 85:
                node_name = db.one("SELECT name FROM nodes WHERE id=?", (node_id,))
                if node_name:
                    warnings.append({
                        "node_id": node_id,
                        "node_name": node_name["name"],
                        "disk_pct": pct,
                        "disk_used_gb": disk_used,
                        "disk_total_gb": disk_total,
                    })
    return warnings