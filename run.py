#!/usr/bin/env python3
"""启动开发服务器: python run.py  → http://<host>:8088"""
import os

import uvicorn

from app import config

if __name__ == "__main__":
    uvicorn.run("app.main:app",
                host=os.environ.get("LXCP_BIND", "0.0.0.0"),
                port=config.HOST_PORT,
                log_level="info")
