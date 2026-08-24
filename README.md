# LXC Deck · 轻量级 LXC 管理面板

> 参照 [NodeHatch](https://docs.nodehatch.com/zh/) 的产品思路设计的多节点 LXC 管理面板：
> 面板本身可安装在任何服务器上，通过 SSH 接入目标机器远程管理其上的 LXC；
> FastAPI + SQLite 后端，零构建原生 JS 前端，另提供演示节点模式供无 LXC 环境体验。

![dashboard](docs/shot-dash.png)

---

## 1. 功能一览

| 模块 | 能力 |
|---|---|
| 📊 概览 | CPU / 内存 / 磁盘环形仪表、实时负载趋势图(120 点)、网络吞吐、TOP5 占用实例、最近动态 |
| 🖧 节点管理 | 三种接入方式：**Agent 反向连接（推荐，支持 NAT）** / SSH / 演示节点；一键安装 LXC、实时指标流；一键生成 Agent **清理/卸载命令**；凭据 Fernet 加密存储 |
| 🔗 订阅中心 | 对标 X-UI-Server：面板级订阅令牌，`/api/sub/{token}` 按 UA 自动适配 Base64 分享链接 / Clash.Meta(mihomo) YAML（8合1 全协议），管理员可随时重置令牌 |
| 🖥 双控制台 | 小鸡(容器)与母机(节点本体)均可开 Web 终端：SSH 直连 PTY / Agent PTY-over-Polling(快轮询低延迟) / 演示模拟；前端 MiniTerm 渲染 ANSI，支持 top/vim/Ctrl+C/Tab/方向键 |
| ⚡ 一键部署 | 移植 X-UI-Server：**8合1 协议矩阵**（XTLS-Reality/Hysteria2/TUIC/Trojan/H2+Reality/gRPC+Reality/AnyTLS/Naive）与单协议下发，直接装进指定 LXC 容器；自动生成 Reality 密钥对/自签证书/DNAT 端口映射/分享链接 |
| 📦 容器实例 | 按节点创建/管理，内存 64MB 起步（64MB 步进，支持 128M/256M 等小规格）、启动 / 停止 / 重启 / 删除、真实 cgroup 指标回显 |
| 🖥 Web 控制台 | WebSocket 全双工伪终端，支持 `ls` `free` `df` `top` `ip a` `ping` `neofetch` 等命令、命令历史(↑↓)、Ctrl+L 清屏 |
| 🗂 镜像模板 | Ubuntu / Debian / Alpine / Rocky / CentOS Stream / Fedora / Arch 卡片式模板库，一键从模板创建 |
| 📸 快照备份 | 创建 / 回滚 / 删除快照，跨实例汇总视图 |
| 🌐 网络 | 网桥(lxcbr)状态、子网 / 网关 / DHCP 范围、地址池用量进度条、IP 分配明细 |
| 👥 用户管理 | 管理员 / 普通用户两级角色、创建 / 删除用户、自助改密 |
| 🛡 安全 | JWT 鉴权、PBKDF2 口令哈希、登录失败 5 次锁定 IP 10 分钟、全量审计日志 |
| 📜 审计日志 | 登录、实例操作、快照、用户变更全量留痕，动作着色筛选 |
| ⚙️ 设置 | 运行模式识别、修改密码、一键重置演示数据 |

## 2. 快速开始

```bash
pip install -r requirements.txt     # fastapi / uvicorn / psutil
python run.py                       # 默认 0.0.0.0:8088
# 浏览器打开 http://<ip>:8088
```

默认账号：`admin / admin123`（管理员）、`ops / ops123`（普通用户）

> 未检测到 `lxc-start` 时面板自动进入**演示模式**：全部功能可交互，
> 容器指标为随机游走仿真、终端为模拟 Shell。宿主机安装 LXC 后重启面板即自动切换真实驱动。

## 3. 架构设计

```
┌──────────────────── 浏览器 SPA (web/) ────────────────────┐
│  原生 JS 路由 · Canvas 图表 · fetch(Bearer JWT) · WS 终端   │
└──────────────▲──────────────────────▲─────────────────────┘
        REST /api/*                WS /ws/terminal/{id}
┌──────────────┴──────────────────────┴─────────────────────┐
│                     FastAPI (app/)                        │
│  routes.py: auth / containers / templates / snapshots /   │
│             network / users / audit / admin               │
├───────────────────────────────────────────────────────────┤
│                   驱动层 lxc.py (核心抽象)                  │
│    MockDriver(演示)  ⇄  RealLXCDriver(lxc-* CLI)           │
│    接口: start/stop/restart/create/delete/live/shell       │
├───────────────────────────────────────────────────────────┤
│   SQLite data/panel.db          monitor.py (psutil 采集)   │
│   users/containers/snapshots    每秒 tick: 网络速率 +       │
│   templates/audit               Mock 指标推进              │
└───────────────────────────────────────────────────────────┘
```

### 关键决策
- **DB 是配置事实源，Driver 是运行时执行者**：容器定义(IP/CPU/内存)入库，启停等动作委托驱动，二者解耦后可平滑替换为 LXD REST 或 libvirt-lxc。
- **驱动接口只有 7 个方法**：对接新运行时 = 实现 `BaseDriver` 子类，一行注册即可。
- **自签 HMAC Token**（JWT 兼容格式）+ PBKDF2 口令哈希，零第三方安全依赖。
- **前端无构建链**：单 HTML + CSS + JS，Canvas 手绘仪表盘/折线图，任何静态服务器可托管。

### 数据模型

```
users(id, username✦, pw_hash, role, created_at)
containers(id, uuid✦, name✦, node, template→templates.key,
           status[running|stopped], cpu, mem MB, disk GB, ip✦, note, created_at)
snapshots(id, container_id→containers, name, size_mb, created_at)
templates(id, key✦, name, distro, version, size_mb, arch)
audit(id, username, action, target, detail, ip, created_at)
```

## 4. API 一览

| 方法 & 路径 | 说明 | 权限 |
|---|---|---|
| `GET  /api/meta` | 品牌 / 版本 / 运行模式 | 公开 |
| `POST /api/login` | 登录换取 Token | 公开 |
| `GET  /api/me` · `POST /api/me/password` | 当前用户 / 改密 | 登录 |
| `GET  /api/overview` | 宿主指标 + 计数 + TOP5 | 登录 |
| `GET/POST /api/containers` | 列表(q/status 过滤) / 创建 | 登录 |
| `POST /api/containers/{id}/action` | start·stop·restart | 登录 |
| `DELETE /api/containers/{id}` | 删除并释放 IP | **管理员** |
| `GET  /api/templates` | 模板列表 | 登录 |
| `GET/POST /api/snapshots` 等 | 快照增删查 / 回滚 | 登录 |
| `GET  /api/network` | 网桥 + IP 分配 | 登录 |
| `GET/POST/DELETE /api/users[...]` | 用户管理 | 查看=登录 写=**管理员** |
| `GET  /api/audit?limit=` | 审计日志 | 登录 |
| `POST /api/admin/reset-demo` | 重置演示数据 | **管理员** |
| `WS   /ws/terminal/{cid}?token=` | 交互式终端 | 登录 |

统一错误格式 `{"detail": "..."}`；所有写操作自动写入审计表。

## 5. 对接真实 LXC

1. 安装：`apt install lxc`（面板重启后徽标变为「已连接真实 LXC」）
2. 授权：为面板运行账号配置 sudo 白名单
   ```
   panel ALL=(ALL) NOPASSWD: /usr/bin/lxc-start, /usr/bin/lxc-stop,
         /usr/bin/lxc-create, /usr/bin/lxc-destroy, /usr/bin/lxc-info
   ```
3. 如需远程多节点，把 `RealLXCDriver._run` 的本地 subprocess 换成 SSH 或在每台节点部署轻量 Agent（见 Roadmap）。

## 6. 生产加固清单

- [ ] 更换 `LXCP_SECRET` 环境变量（默认值仅供演示）
- [ ] Nginx 反代 + TLS；`/ws/` 需开启 Upgrade 头
- [ ] 面板进程以非 root 运行，仅 sudo 白名单放行 lxc 命令
- [ ] SQLite → PostgreSQL（多面板实例时）；审计表按月归档
- [ ] 终端接入真实 PTY（ttyd / lxc-attach），替换 Mock Shell
- [ ] 登录失败速率限制 + 双因素认证

## 7. Roadmap

- 多节点管理与 Agent 心跳（对标 NodeHatch 的 Node 概念）
- LXD REST API 驱动（支持迁移、实时监控 CGroup 指标）
- WebSSH 文件管理器(SFTP)、批量操作
- 备份到 S3/OSS、定时快照策略
- 工单 / 计费 / 套餐配额（面向售卖场景）

## 8. 目录结构

```
lxcdeck/
├── run.py                  # 启动入口 (uvicorn :8088)
├── requirements.txt
├── app/
│   ├── config.py           # 配置与模式自动检测
│   ├── db.py               # SQLite 封装 + 建表 + 种子数据
│   ├── security.py         # PBKDF2 + HMAC Token
│   ├── lxc.py              # 驱动层: MockDriver / RealLXCDriver + 模拟Shell
│   ├── monitor.py          # psutil 宿主采集 + 每秒 tick 循环
│   ├── routes.py           # 全部 REST 路由
│   └── main.py             # FastAPI 组装 + WS 终端 + 静态托管
└── web/
    ├── index.html
    ├── css/style.css       # 深色主题设计系统
    └── js/app.js           # SPA: 路由 / 视图 / Canvas 图表 / 终端
```
