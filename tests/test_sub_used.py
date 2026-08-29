"""订阅「已使用」流量显示修复的冒烟测试
根因：userinfo_header 硬编码 upload=0; download=0 → 客户端「已使用」恒为 0。
修复：面板订阅用订阅内节点真实流量（traffic_daily，status='done' 口径）；
      转换订阅手动模式下保留上游真实已使用，total = 已使用 + 手动剩余。"""
import os
import sys
import tempfile

_tmpdb = os.path.join(tempfile.mkdtemp(prefix="usedt_"), "panel.db")
os.environ["LXCP_DB"] = _tmpdb            # 测试隔离：绝不碰仓库 data/panel.db
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

GIB = 1024 ** 3
PASS, FAIL = [], []


def chk(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  [{extra}]" if extra and not cond else ""))


def parse_hdr(h: str) -> dict:
    out = {}
    for part in h.replace(" ", "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                out[k] = int(v)
            except ValueError:
                out[k] = v
    return out


print("== 准备：节点 / 应用 / 流量数据 ==")
from app import db
db.connect()
db.init_schema()
from app import traffic as traffic_mod
traffic_mod.init_tables()

db.ex("INSERT INTO nodes(name,kind,created_at) VALUES('n1','agent',?), ('n2','agent',?)", db.now(), db.now())
n1, n2 = 1, 2
# n1：订阅内节点（done 应用）；n2：不在订阅（failed 应用）
db.ex("INSERT INTO apps(node_id,name,app_type,status,created_at) VALUES(?,'a1','proxy','done',?)", n1, db.now())
db.ex("INSERT INTO apps(node_id,name,app_type,status,created_at) VALUES(?,'a2','proxy','failed',?)", n2, db.now())
# n1 流量：rx=2GiB tx=1GiB；n2 流量更大但不应计入
db.ex("INSERT INTO traffic_daily(node_id,date,rx_bytes,tx_bytes) VALUES(?,'2026-08-28',?,?)", n1, 2 * GIB, 1 * GIB)
db.ex("INSERT INTO traffic_daily(node_id,date,rx_bytes,tx_bytes) VALUES(?,'2026-08-29',?,?)", n1, 2 * GIB, 1 * GIB)
db.ex("INSERT INTO traffic_daily(node_id,date,rx_bytes,tx_bytes) VALUES(?,'2026-08-29',?,?)", n2, 50 * GIB, 50 * GIB)

print("== 1. 面板订阅 userinfo（subscribe.py） ==")
from app import subscribe as sub
h = parse_hdr(sub.userinfo_header())
chk("已使用=真实流量(Σrx=4G,Σtx=2G)", h["upload"] == 2 * GIB and h["download"] == 4 * GIB, str(h))
chk("无手动 → total=9999G", h["total"] == 9999 * GIB, str(h))
t = sub.get_sub_traffic()
chk("get_sub_traffic 带 used_gb=6.0", abs(t["used_gb"] - 6.0) < 0.01, str(t))
chk("failed 应用节点流量不计入", h["upload"] + h["download"] == 6 * GIB)

sub.set_sub_traffic(100, "")
h = parse_hdr(sub.userinfo_header())
chk("手动剩余100G → total=已使用6G+100G", h["total"] == 6 * GIB + 100 * GIB, str(h))
chk("手动模式下已使用仍显示真实值", h["upload"] + h["download"] == 6 * GIB)
sub.set_sub_traffic(50, "2026-12-31")
h = parse_hdr(sub.userinfo_header())
chk("到期日写入 expire", "expire" in h and h["expire"] > 0, str(h))
sub.set_sub_traffic(None, "")
h = parse_hdr(sub.userinfo_header())
chk("清除手动 → 回退 9999G 且已使用保留", h["total"] == 9999 * GIB and h["download"] == 4 * GIB)

print("== 2. 转换订阅 userinfo（subconv.py） ==")
from app import subconv as sc
ups = "upload=1073741824; download=2147483648; total=10737418240; expire=1800000000"
h = parse_hdr(sc.userinfo_header(None, "", ups))
chk("无手动 → 原样透传机场头", h["upload"] == 1073741824 and h["total"] == 10737418240
    and h.get("expire") == 1800000000, str(h))
h = parse_hdr(sc.userinfo_header(5, "", ups))
chk("手动剩余5G+上游已用3G → total=8G", h["total"] == (1 + 2 + 5) * GIB, str(h))
chk("手动模式保留机场真实已使用", h["upload"] == 1 * GIB and h["download"] == 2 * GIB)
chk("手动未填到期 → 沿用上游 expire", h.get("expire") == 1800000000, str(h))
h = parse_hdr(sc.userinfo_header(5, "2026-12-31", ups))
chk("手动到期优先于上游", h.get("expire") == sc._expire_epoch("2026-12-31"), str(h))
h = parse_hdr(sc.userinfo_header(None, "", ""))
chk("无上游无手动 → 默认 9999G/已用0", h["upload"] == 0 and h["total"] == 9999 * GIB, str(h))
h = parse_hdr(sc.userinfo_header(5, "", "garbage-without-total"))
chk("垃圾上游 → 按默认处理(已用0)", h["upload"] == 0 and h["total"] == 5 * GIB, str(h))
h = parse_hdr(sc.userinfo_header("abc", "", ups))
chk("非法手动值 → 透传上游", h["total"] == 10737418240, str(h))

print()
print(f"PASS {len(PASS)} / FAIL {len(FAIL)}")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
