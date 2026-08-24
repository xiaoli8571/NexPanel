"""全局配置"""
import os
import shutil
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"
DB_PATH = os.environ.get("LXCP_DB", str(DATA_DIR / "panel.db"))

SECRET_KEY = os.environ.get("LXCP_SECRET", "dev-secret-change-me-in-production")
TOKEN_TTL = int(os.environ.get("LXCP_TOKEN_TTL", str(86400 * 7)))  # 7 天
HOST_PORT = int(os.environ.get("LXCP_PORT", "8088"))

VERSION = "v0.6.0"

# 自动检测：宿主机存在 lxc-start 时进入真实模式，否则为演示(Mock)模式
REAL_LXC = shutil.which("lxc-start") is not None

try:
    HOSTNAME = os.uname().nodename
except Exception:            # pragma: no cover
    HOSTNAME = "localhost"

BRAND = "LXC Deck"

# 面板对外访问地址(生成 Agent 安装命令用)，留空则从请求推断
PUBLIC_BASE = os.environ.get("LXCP_PUBLIC_BASE", "").rstrip("/")
