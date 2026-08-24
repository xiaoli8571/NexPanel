"""FastAPI 入口：REST 路由 + WS 终端(演示/SSH 双模式) + 静态资源"""
import asyncio
import json
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from . import config, db, monitor, nodes as nodes_mod
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


# ────────────── 演示节点：模拟 Shell 会话 ──────────────
async def _demo_terminal(ws: WebSocket, c: dict):
    from .lxc import DemoRuntime
    rt = monitor.demo_runtime(c["node_id"])
    banner = (f"Linux {c['name']} 5.15.0-91-generic x86_64 (simulated)\r\n"
              f"输入 'help' 查看可用命令。\r\n")
    await ws.send_text(json.dumps({"type": "out", "text": banner}, ensure_ascii=False))
    while True:
        line = await ws.receive_text()
        out = rt.shell(c, line)
        if out is None:
            await ws.send_text(json.dumps({"type": "clear"}))
            continue
        if out == "__EXIT__":
            await ws.send_text(json.dumps({"type": "out", "text": "logout\r\n"}))
            break
        await asyncio.sleep(0.12)
        await ws.send_text(json.dumps({"type": "out", "text": out + "\r\n"},
                                      ensure_ascii=False))


# ────────────── SSH 节点：PTY 桥接 lxc-attach ──────────────
async def _ssh_terminal(ws: WebSocket, c: dict, node: dict):
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
            if data:
                text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
                try:
                    await ws.send_text(json.dumps({"type": "out", "text": text},
                                                  ensure_ascii=False))
                except Exception as e:
                    print(f"[ws-terminal] send failed: {e!r}", flush=True)
                    break

    try:
        cli = await asyncio.to_thread(nodes_mod.connect, node)
        chan = await asyncio.to_thread(cli.invoke_shell, "xterm-256color", 120, 32)
        chan.settimeout(2.0)
        task = asyncio.create_task(pump())
        await asyncio.sleep(2.0)          # 等远端 banner/提示符
        print(f"[ws-terminal] sending attach for {c['name']}", flush=True)
        chan.send(f"lxc-attach -n {c['name']}\n")
        await ws.send_text(json.dumps({"type": "out",
            "text": f"[面板] 已连接节点 {node['name']}，进入容器 {c['name']}...\r\n"},
            ensure_ascii=False))
        try:
            while True:
                msg = await ws.receive_text()
                if msg == "__RESIZE__":
                    continue
                chan.send(msg + "\n")
        except WebSocketDisconnect:
            pass
        finally:
            closed["v"] = True
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
    except Exception as e:
        with suppress(Exception):
            await ws.send_text(json.dumps(
                {"type": "out", "text": f"\r\n[面板] 连接节点失败: {e}\r\n"},
                ensure_ascii=False))
    finally:
        closed["v"] = True
        for closer in ((lambda: chan.close()) if chan else None,
                       (lambda: cli.close()) if cli else None):
            if closer:
                with suppress(Exception):
                    await asyncio.to_thread(closer)
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
    if node and node["kind"] == "ssh":
        await _ssh_terminal(ws, c, dict(node))
    elif node:
        await _demo_terminal(ws, c)
    else:
        await ws.send_text(json.dumps({"type": "out",
                                       "text": "[面板] 实例未关联有效节点\r\n"}))
        await ws.close()


# ────────────── 静态前端(置于 API 之后) ──────────────
app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="web")
