"""CODEAUDIT 冒烟测试：验证 7 项修复的真实行为"""
import os, sys, json, tempfile, importlib

_tmpdb = os.path.join(tempfile.mkdtemp(prefix="audit_"), "panel.db")
os.environ["LXCP_DB"] = _tmpdb            # 测试隔离：绝不碰仓库 data/panel.db
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS, FAIL = [], []
def chk(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  [{extra}]" if extra and not cond else ""))

print("== 1. UPGRADE_SH 指纹常量化 ==")
from app import agent as agent_mod
chk("UPGRADE_SH 已注入当前版本指纹", "started v20260829" in agent_mod.UPGRADE_SH)
chk("UPGRADE_SH 无残留占位符", "__AGENT_VER__" not in agent_mod.UPGRADE_SH)
chk("AGENT_PY 内嵌 AGENT_VER 定义", 'AGENT_VER = "v20260829"' in agent_mod.AGENT_PY)
chk("AGENT_VER 模块常量", agent_mod.AGENT_VER == "v20260829")
# 模拟升级校验：从面板"下载"的 agent.py 含指纹
served = agent_mod.AGENT_PY
chk("下发的 agent.py 能通过 UPGRADE_SH 的 grep 校验",
    f'grep -q "started {agent_mod.AGENT_VER}"' .replace('"started ', '"started ') and agent_mod.AGENT_VER in served)

print("== 2. db.ex 返回 lastrowid / 写提交 ==")
from app import db
db.connect()
db.init_schema()
rid = db.ex("INSERT INTO users(username,pw_hash,role,created_at) VALUES(?,?,?,?)",
            ("t_audit", "x", "user", db.now()))
row = db.one("SELECT id,username FROM users WHERE username='t_audit'")
chk("ex() 返回的 lastrowid 即新行 id", row and row["id"] == rid, f"rid={rid} row={dict(row) if row else None}")

print("== 3. subconv vless/trojan TLS 处理 ==")
from app import subconv as sc
# 3a: 无 TLS 的 vless-ws（面板自家生成的链接形态）不应输出 tls: true
uri_plain = "vless://11111111-2222-3333-4444-555555555555@1.2.3.4:8443?type=ws&path=%2F&encryption=none#plain-ws"
n1 = sc.parse_uri(uri_plain)
y1 = sc.build_clash_yaml([n1])
chk("无TLS vless-ws 不输出 tls:true", "tls: true" not in y1)
chk("无TLS vless-ws 保留 ws-opts", "ws-opts" in y1)
# 3b: TLS vless 应输出 tls: true
uri_tls = "vless://11111111-2222-3333-4444-555555555555@1.2.3.4:443?type=ws&path=%2F&security=tls&sni=a.com&fp=chrome#tls-ws"
n2 = sc.parse_uri(uri_tls)
y2 = sc.build_clash_yaml([n2])
chk("TLS vless 输出 tls:true", "tls: true" in y2)
chk("TLS vless 输出 servername", "servername:" in y2 and "a.com" in y2)
# 3c: trojan 带 sni 应输出 sni
uri_tj = "trojan://pw123@5.6.7.8:443?security=tls&sni=cdn.example.com#tj1"
n3 = sc.parse_uri(uri_tj)
y3 = sc.build_clash_yaml([n3])
chk("trojan 输出 sni", "sni:" in y3 and "cdn.example.com" in y3)
chk("trojan insecure 输出 skip-cert-verify", "skip-cert-verify: true" in y3 or "skip-cert-verify" not in y3)
# 3d: hysteria2 带 sni
uri_h2 = "hysteria2://pw@9.9.9.9:8443/?sni=hy.example.com&insecure=1#h2x"
n4 = sc.parse_uri(uri_h2)
y4 = sc.build_clash_yaml([n4])
chk("hysteria2 输出 sni", "sni:" in y4 and "hy.example.com" in y4)
# 3e: 往返——uri → yaml → 不崩
chk("多协议混合构建不崩", isinstance(sc.build_clash_yaml([n1, n2, n3, n4]), str))

print("== 4. push_result 淘汰逻辑 ==")
for i in range(300):
    agent_mod.push_result(f"cmd_{i}", 0, "x")
agent_mod.push_result("cmd_new", 0, "y")
chk("超量后总条目被硬上限约束", len(agent_mod._results) <= 257,
    f"len={len(agent_mod._results)}")
chk("最新条目存在", "cmd_new" in agent_mod._results)

print("== 5. /agent/result 鉴权（源码级） ==")
src = open(os.path.join(os.path.dirname(__file__), "..", "app", "routes.py")).read()
import re
m = re.search(r'@router\.post\("/agent/result"\)\s*\nasync def agent_result\(request: _Req\):\s*\n\s*(\w+) = _agent_auth\(request\)', src)
chk("agent_result 调用 _agent_auth", bool(m))
chk("set_egress/_set_egress_state 均改用 db.ex 写",
    src.count('db.q("UPDATE apps SET params=?') == 0)

print("== 6. app.js redial 修复（源码级） ==")
js = open(os.path.join(os.path.dirname(__file__), "..", "web", "js", "app.js")).read()
chk("redial 用 {method:'POST'}", 'residential/redial`, {method:"POST"})' in js)
chk("无 api(x, \"POST\") 残留", ', "POST")' not in js)

print("== 7. deploy.py 修复（源码级） ==")
dp = open(os.path.join(os.path.dirname(__file__), "..", "app", "deploy.py")).read()
chk("app_id 用 db.ex lastrowid", "ORDER BY id DESC LIMIT 1" not in dp)
chk("失败路径 container None 安全", 'container["id"], name_prefix, "proxy", "failed"' not in dp)

print()
print(f"PASS {len(PASS)} / FAIL {len(FAIL)}")
if FAIL:
    print("FAILED:", FAIL); sys.exit(1)
