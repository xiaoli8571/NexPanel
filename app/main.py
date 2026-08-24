"""FastAPI 入口：REST 路由 + WS 终端(SSH / Agent PTY / 演示 三通道) + 静态资源"""
import asyncio
import json
import shlex
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from . import config, db, monitor, nodes as nodes_mod
from . import agent as agent_mod
from . import security
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    db.init_schema()
    db.seed()
    monitor.start_all()
    yield
    await monitor.shutdown()


app = FastAPI(title="LXC Deck", version=config.VERSION, lifespan=lifespan)
app.include_router(router)


def _auth_ws(token: str):
    return security.decode_token(token) if token else None


async def _ws_out(ws: WebSocket, text: str):
    with suppress(Exception):
        await ws.send_text(json.dumps({"type": "out", "text": text}, ensure_ascii=False))


# ══════════════ 演示节点：模拟 Shell 会话（行编辑 + 回显） ══════════════
async def _demo_terminal(ws: WebSocket, c: dict):
    from .lxc import DemoRuntime
    rt = monitor.demo_runtime(c["node_id"])
    banner = (f"Linux {c['name']} 5.15.0-91-generic x86_64 (simulated)\r\n"
              f"输入 'help' 查看可用命令。\r\n")
    await _ws_out(ws, banner)
    prompt = f"root@{c['name']}:~# "
    buf = ""

    async def prompt_():
        await _ws_out(ws, prompt)

    await prompt_()
    while True:
        try:
            raw = await ws.receive_text()
            msg = json.loads(raw)
        except WebSocketDisconnect:
            return
        except Exception:
            continue
        if msg.get("type") == "resize":
            continue
        data = str(msg.get("data") or "")
        out_all = ""
        for ch in data:
            if ch in ("\r", "\n"):
                line, buf = buf, ""
                out_all += "\r\n"
                res = rt.shell(c, line) if line.strip() else ""
                if res is None:
                    await ws.send_text(json.dumps({"type": "clear"}))
                    out_all = ""
                    break
                if res == "__EXIT__":
                    await _ws_out(ws, "logout\r\n")
                    with suppress(Exception):
                        await ws.close()
                    return
                if res:
                    out_all += res + "\r\n"
            elif ch in ("\x7f", "\x08"):
                if buf:
                    buf = buf[:-1]
                    out_all += "\b \b"
            elif ch == "\x03":                      # Ctrl+C
                buf = ""
                out_all += "^C\r\n"
            elif ch == "\x04":                      # Ctrl+D
                await _ws_out(ws, "logout\r\n")
                with suppress(Exception):
                    await ws.close()
                return
            elif ch == "\x15":                      # Ctrl+U
                out_all += "\b \b" * len(buf)
                buf = ""
            elif ch >= " ":
                buf += ch
                out_all += ch
        if out_all:
            await _ws_out(ws, out_all + (prompt if not buf else ""))
        else:
            await prompt_()


# ────────────── SSH 节点：PTY 桥接（容器 lxc-attach / 母机直连 通用） ──────────────
async def _ssh_terminal(ws: WebSocket, node: dict, c: dict | None = None):
    cli = None
    chan = None
    closed = {"v": False}

    async def pump():
        """远端 → 浏览器（recv 超时属正常轮询，不视为断开）"""
        import socket as _s
        while not closed["v"]:
            try:
                data = await asyncio.to_thread(chan.recv, 4096)
            except (TimeoutError, _s.timeout):
                continue
            except Exception:
                break
            if not data:
                break
            text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
            try:
                await ws.send_text(json.dumps({"type": "out", "text": text},
                                              ensure_ascii=False))
            except Exception as e:
                print(f"[ws-terminal] send failed: {e!r}", flush=True)
                break

    async def bridge():
        """浏览器 JSON 信封 → 远端 PTY"""
        while not closed["v"]:
            try:
                raw = await ws.receive_text()
                msg = json.loads(raw)
            except WebSocketDisconnect:
                return
            except Exception:
                continue
            if closed["v"]:
                return
            if msg.get("type") == "input":
                chan.send(str(msg.get("data") or ""))
            elif msg.get("type") == "resize":
                try:
                    cols = max(40, min(int(msg.get("cols") or 120), 500))
                    rows = max(8, min(int(msg.get("rows") or 32), 300))
                    chan.resize_pty(width=cols, height=rows)
                except Exception:
                    pass

    try:
        cli = await asyncio.to_thread(nodes_mod.connect, node)
        chan = await asyncio.to_thread(cli.invoke_shell, "xterm-256color", 120, 32)
        chan.settimeout(2.0)
        task = asyncio.create_task(pump())
        await asyncio.sleep(1.5)          # 等远端 banner/提示符
        if c:
            chan.send(f"lxc-attach -n {shlex.quote(c['name'])}\n")
            print(f"[ws-terminal] sending attach for {c['name']}", flush=True)
            await _ws_out(ws, f"[面板] 已连接节点 {node['name']}，进入容器 {c['name']}...\r\n")
        else:
            await _ws_out(ws, f"[面板] 已连接母机 {node['host'] or node['name']}...\r\n")
        await bridge()
    except Exception as e:
        with suppress(Exception):
            await _ws_out(ws, f"\r\n[面板] 连接节点失败: {e}\r\n")
    finally:
        closed["v"] = True
        for closer in ((lambda: chan.close()) if chan else None,
                       (lambda: cli.close()) if cli else None):
            if closer:
                with suppress(Exception):
                    await asyncio.to_thread(closer)
        with suppress(Exception):
            await ws.close()


# ────────────── Agent 节点：PTY-over-Polling 桥接 ──────────────
async def _agent_pty_ws(ws: WebSocket, node: dict, cmd: str):
    nid = node["id"]
    if not agent_mod.is_online(nid):
        await _ws_out(ws, "[面板] Agent 离线，无法建立终端（请检查目标机 lxcdeck-agent 服务）\r\n")
        with suppress(Exception):
            await ws.close()
        return
    sid = agent_mod.open_pty(nid, cmd)
    q = agent_mod._pty_subs[sid]
    print(f"[ws-terminal] agent pty {sid} @node{nid}: {cmd[:60]}", flush=True)

    async def pump():
        while True:
            chunk = await q.get()
            if chunk == "__CLOSED__":
                await _ws_out(ws, "\r\n[面板] 远端会话已结束。\r\n")
                return
            await _ws_out(ws, chunk)

    pt = asyncio.create_task(pump())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") == "input":
                agent_mod.pty_input(sid, str(msg.get("data") or ""))
            elif msg.get("type") == "resize":
                agent_mod.pty_resize(sid, int(msg.get("cols") or 120),
                                     int(msg.get("rows") or 32))
    except WebSocketDisconnect:
        pass
    finally:
        pt.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await pt
        agent_mod.close_pty(sid)
        with suppress(Exception):
            await ws.close()


@app.websocket("/ws/terminal/{cid}")
async def terminal(ws: WebSocket, cid: int, token: str = ""):
    payload = _auth_ws(token)
    if not payload:
        await ws.close(code=4401)
        return
    row = db.one("SELECT * FROM containers WHERE id=?", (cid,))
    if not row:
        await ws.close(code=4404)
        return
    c = dict(row)
    node = db.one("SELECT * FROM nodes WHERE id=?", (c["node_id"],)) if c["node_id"] else None
    await ws.accept()
    if not node:
        await _ws_out(ws, "[面板] 实例未关联有效节点\r\n")
        with suppress(Exception):
            await ws.close()
        return
    n = dict(node)
    if n["kind"] == "ssh":
        await _ssh_terminal(ws, n, c)
    elif n["kind"] == "agent":
        await _agent_pty_ws(ws, n,
                                f"lxc-attach -n {shlex.quote(c['name'])} 2>&1 || "
                                f"echo '[agent] 无法进入容器（不存在或未运行）'")
    else:
        await _demo_terminal(ws, c)


@app.websocket("/ws/node-terminal/{nid}")
async def node_terminal(ws: WebSocket, nid: int, token: str = ""):
    """母机(节点本体)控制台：SSH 直连 / Agent PTY / 演示模拟"""
    payload = _auth_ws(token)
    if not payload:
        await ws.close(code=4401)
        return
    row = db.one("SELECT * FROM nodes WHERE id=?", (nid,))
    if not row:
        await ws.close(code=4404)
        return
    n = dict(row)
    await ws.accept()
    if n["kind"] == "ssh":
        await _ssh_terminal(ws, n, None)
    elif n["kind"] == "agent":
        await _agent_pty_ws(ws, n, "bash -li")
    else:
        fake = {"name": n["name"], "template": "ubuntu-22.04", "cpu": 4,
                "mem": 4096, "disk": 40, "status": "running"}
        await _demo_terminal(ws, fake)


# ────────────── 静态前端(置于 API 之后) ──────────────
app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="web")
