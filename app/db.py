"""SQLite 存储层：连接、建表、迁移、种子数据

多节点版：
* nodes        被接入的服务器(SSH)或演示节点
* containers   挂在某个节点下 (node_id)
* 迁移策略      检测到旧单机表结构时自动重建，并清除历史演示实例数据
"""
import sqlite3
import threading
import pathlib
from datetime import datetime

from . import config, security

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()


def connect():
    global _conn
    pathlib.Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


def _norm(args):
    if len(args) == 1 and isinstance(args[0], (tuple, list)):
        return tuple(args[0])
    return args


def q(sql: str, *p):
    with _lock:
        return _conn.execute(sql, _norm(p)).fetchall()


def one(sql: str, *p):
    with _lock:
        return _conn.execute(sql, _norm(p)).fetchone()


def ex(sql: str, *p):
    with _lock:
        _conn.execute(sql, _norm(p))
        _conn.commit()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  pw_hash  TEXT NOT NULL,
  role     TEXT NOT NULL DEFAULT 'user',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL DEFAULT 'ssh',            -- agent | ssh | demo
  host TEXT DEFAULT '',
  port INTEGER DEFAULT 22,
  username TEXT DEFAULT '',
  auth_type TEXT DEFAULT 'password',
  secret TEXT DEFAULT '',
  agent_token TEXT DEFAULT '',
  public_ip TEXT DEFAULT '',
  last_seen TEXT DEFAULT '',
  role TEXT DEFAULT 'manage',                  -- manage(全面接管) | probe(仅监控)
  status TEXT DEFAULT 'unknown',
  os_info TEXT DEFAULT '',
  lxc_ok INTEGER DEFAULT 0,
  install_lxc INTEGER DEFAULT 0,      -- 0=仅部署节点(不装LXC) 1=作为母机(自动装LXC)
  lxc_install_ts TEXT DEFAULT '',     -- 最近一次自动安装LXC的时间戳(去重)
  sort_order INTEGER DEFAULT 0,       -- 节点排序
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS containers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid TEXT UNIQUE NOT NULL,
  name TEXT UNIQUE NOT NULL,
  node_id INTEGER,
  template TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'stopped',
  cpu INTEGER NOT NULL DEFAULT 1,
  mem INTEGER NOT NULL DEFAULT 512,
  disk INTEGER NOT NULL DEFAULT 5,
  ip TEXT DEFAULT '',
  note TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  container_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  size_mb REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS apps(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  container_id INTEGER,
  node_id INTEGER,
  name TEXT NOT NULL,
  app_type TEXT NOT NULL,
  params TEXT DEFAULT '{}',
  links TEXT DEFAULT '[]',
  dnat_rules TEXT DEFAULT '[]',
  status TEXT DEFAULT 'pending',
  log TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT, action TEXT, target TEXT, detail TEXT, ip TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS templates(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  distro TEXT NOT NULL,
  version TEXT NOT NULL,
  size_mb REAL NOT NULL,
  arch TEXT NOT NULL DEFAULT 'amd64'
);
"""

SEED_USERS = [
    ("admin", "admin123", "admin"),
    ("ops",   "ops123",   "user"),
]

SEED_TEMPLATES = [
    ("debian-12",        "Debian 12",        "debian",  "12 (bookworm)", 148),
    ("alpine-3.19",      "Alpine Linux",     "alpine",  "3.19",          8),
    ("archlinux",        "Arch Linux",       "arch",    "rolling",       165),
]


def init_schema():
    _conn.executescript(SCHEMA)
    migrate()
    _conn.commit()


def migrate():
    """渐进式迁移"""
    cols = [r[1] for r in _conn.execute("PRAGMA table_info(containers)")]
    if cols and "node_id" not in cols:
        _conn.execute("DROP TABLE containers")
        _conn.execute("DELETE FROM snapshots")
        _conn.executescript(SCHEMA)
        print("[db] migrated: legacy demo containers removed")
    # apps 表补 node_id（主机直装或容器所在节点）
    acols = [r[1] for r in _conn.execute("PRAGMA table_info(apps)")]
    if acols and "node_id" not in acols:
        _conn.execute("ALTER TABLE apps ADD COLUMN node_id INTEGER")
        # 回填：容器部署 → 从 containers.node_id 取；主机直装 → 按 name 匹配 nodes.name
        _conn.execute("UPDATE apps SET node_id = (SELECT c.node_id FROM containers c WHERE c.id = apps.container_id) WHERE node_id IS NULL AND container_id IS NOT NULL")
        _conn.execute("UPDATE apps SET node_id = (SELECT n.id FROM nodes n WHERE n.name = apps.name) WHERE node_id IS NULL AND container_id IS NULL")
        _conn.commit()
        print("[db] apps.node_id added and backfilled")

    # nodes 表补 agent 相关列 + 排序
    ncols = [r[1] for r in _conn.execute("PRAGMA table_info(nodes)")]
    for col, ddl in (("agent_token", "TEXT DEFAULT ''"),
                     ("public_ip", "TEXT DEFAULT ''"),
                     ("last_seen", "TEXT DEFAULT ''"),
                     ("role", "TEXT DEFAULT 'manage'"),
                     ("install_lxc", "INTEGER DEFAULT 0"),
                     ("lxc_install_ts", "TEXT DEFAULT ''"),
                     ("sort_order", "INTEGER DEFAULT 0")):
        if ncols and col not in ncols:
            _conn.execute(f"ALTER TABLE nodes ADD COLUMN {col} {ddl}")
            print(f"[db] nodes.{col} added")

    # 模板库只保留 alpine / debian / arch
    keep = ("alpine-3.19", "debian-12", "archlinux")
    _conn.execute("DELETE FROM templates WHERE key NOT IN (?,?,?)", keep)
    _conn.commit()
    print("[db] templates pruned to alpine/debian/arch")


def seed():
    if not one("SELECT id FROM users LIMIT 1"):
        for u, p, r in SEED_USERS:
            ex("INSERT INTO users(username,pw_hash,role,created_at) VALUES(?,?,?,?)",
               u, security.hash_password(p), r, now())

    if not one("SELECT id FROM templates LIMIT 1"):
        for key, name, distro, ver, size in SEED_TEMPLATES:
            ex("INSERT INTO templates(key,name,distro,version,size_mb) VALUES(?,?,?,?,?)",
               key, name, distro, ver, size)


def wipe_instances():
    """清空全部实例与快照（保留节点/用户/模板/审计）"""
    ex("DELETE FROM snapshots")
    ex("DELETE FROM containers")


def audit(username: str, action: str, target: str = "", detail: str = "", ip: str = ""):
    ex("INSERT INTO audit(username,action,target,detail,ip,created_at) VALUES(?,?,?,?,?,?)",
       username, action, target, detail, ip, now())
