"""容器操作层：按节点类型分发

* DemoRuntime  演示节点：纯内存仿真（指标随机游走 + 模拟 Shell）
* SSH 远程     真实节点：通过 nodes.run_cmd 执行 lxc-* 命令
"""
import random
import shlex
import threading
import time

from . import nodes as nodes_mod

# 模板 key → lxc-download 参数
TEMPLATE_IMAGE_MAP = {
    "ubuntu-22.04":    ("ubuntu", "jammy"),
    "ubuntu-24.04":    ("ubuntu", "noble"),
    "debian-12":       ("debian", "bookworm"),
    "alpine-3.19":     ("alpine", "3.22"),        # 镜像源当前提供的 3.x 稳定版
    "rockylinux-9":    ("rockylinux", "9"),
    "centos-stream-9": ("centos", "9-Stream"),
    "fedora-39":       ("fedora", "43"),
    "archlinux":       ("archlinux", "current"),
}

PRETTY_OS = {
    "ubuntu-22.04": "Ubuntu 22.04 LTS", "ubuntu-24.04": "Ubuntu 24.04 LTS",
    "debian-12": "Debian GNU/Linux 12 (bookworm)", "alpine-3.19": "Alpine Linux v3.19",
    "rockylinux-9": "Rocky Linux 9.4 (Blue Onyx)", "centos-stream-9": "CentOS Stream 9",
    "fedora-39": "Fedora Linux 39 (Cloud Edition)", "archlinux": "Arch Linux",
}

HELP_TEXT = """可用命令:
  help / ls / pwd / whoami / hostname / uname [-a]
  uptime / free [-m|-h] / df [-h] / ps / top
  ip a | ifconfig / cat /etc/os-release
  ping <host> / neofetch / clear / exit"""


# ════════════════════ 演示节点运行时 ════════════════════
class DemoRuntime:
    def __init__(self):
        self._lock = threading.Lock()
        self.state: dict[str, dict] = {}

    def _s(self, name):
        return self.state.setdefault(name, {"cpu": 5.0, "mem_used": 64.0,
                                            "rx": 80.0, "tx": 40.0})

    def start(self, c):
        with self._lock:
            self._s(c["name"])["since"] = time.time()

    def stop(self, c):
        with self._lock:
            self.state.pop(c["name"], None)

    def restart(self, c):
        self.stop(c); self.start(c)

    def create(self, c):
        with self._lock:
            self.state[c["name"]] = {"cpu": 2.0, "mem_used": 48.0, "rx": 10.0, "tx": 6.0}

    def delete(self, c):
        with self._lock:
            self.state.pop(c["name"], None)

    def reset(self):
        with self._lock:
            self.state.clear()

    def step(self, containers: list[dict]):
        with self._lock:
            for c in containers:
                s = self.state.setdefault(c["name"], {
                    "cpu": random.uniform(4, 28), "mem_used": c["mem"] * random.uniform(.22, .5),
                    "rx": random.uniform(20, 320), "tx": random.uniform(12, 160)})
                if c["status"] == "running":
                    s.setdefault("since", time.time())
                    cap = min(c["cpu"] * 38 + 12, 96)
                    s["cpu"] = max(1.0, min(cap, s["cpu"] + random.gauss(0, 4)))
                    target = c["mem"] * random.uniform(.35, .68)
                    s["mem_used"] = max(48.0, min(c["mem"] - 32,
                                         s["mem_used"] + (target - s["mem_used"]) * .08 + random.gauss(0, 20)))
                    burst = random.random()
                    m = 3.2 if burst > .93 else (.15 if burst < .05 else 1.0)
                    s["rx"] = max(1, min(90000, s["rx"] * m * random.uniform(.85, 1.18)))
                    s["tx"] = max(1, min(60000, s["tx"] * m * random.uniform(.85, 1.18)))
                else:
                    s.update(cpu=0, mem_used=0, rx=0, tx=0)
                    s.pop("since", None)

    def live(self, c: dict) -> dict:
        with self._lock:
            s = self.state.get(c["name"])
        if not s or c["status"] != "running":
            return {"cpu_pct": 0, "mem_used_mb": 0, "rx_kbps": 0, "tx_kbps": 0, "uptime_s": 0}
        return {"cpu_pct": round(s["cpu"], 1), "mem_used_mb": int(s["mem_used"]),
                "rx_kbps": round(s["rx"]), "tx_kbps": round(s["tx"]),
                "uptime_s": int(time.time() - s.get("since", time.time()))}

    # ---------- 模拟 Shell ----------
    @staticmethod
    def _fmt_upt(sec):
        d, rem = divmod(int(sec), 86400)
        h, rem = divmod(rem, 3600)
        m, _ = divmod(rem, 60)
        return f"{d} days, {h}:{m:02d}" if d else f"{h}:{m:02d}"

    def shell(self, c: dict, line: str) -> str | None:
        cmd = line.strip()
        if not cmd:
            return ""
        low = " ".join(cmd.lower().split())
        name, tpl = c["name"], c["template"]
        live = self.live(c)
        if low == "clear":
            return None
        if low in ("help", "?"):
            return HELP_TEXT
        if low in ("exit", "logout"):
            return "__EXIT__"
        if low == "ls":
            return "bin  boot  dev  etc  home  lib  media  mnt  opt  proc  root  run  sbin  srv  sys  tmp  usr  var"
        if low == "pwd":      return "/root"
        if low == "whoami":   return "root"
        if low == "hostname": return name
        if low.startswith("uname"):
            return f"Linux {name} 5.15.0-91-generic #99-Ubuntu SMP x86_64 GNU/Linux"
        if low == "uptime":
            t = time.strftime("%H:%M:%S")
            l1 = round(live["cpu_pct"] / 100 * c["cpu"], 2)
            return (f" {t} up {self._fmt_upt(live['uptime_s'])},  1 user,  "
                    f"load average: {l1:.2f}, {l1*.8:.2f}, {l1*.65:.2f}")
        if low.startswith("free"):
            total, used = c["mem"], live["mem_used_mb"]
            buff = int(total * .18)
            return (f"{'':14}total     used     free   shared  buff/cache\n"
                     f"Mem:   {total:>8} {used:>8} {max(total-used-buff,0):>8} "
                     f"{16:>7} {buff:>11}")
        if low.startswith("df"):
            used_g = round(c["disk"] * .21, 1)
            return ("Filesystem      Size  Used Avail Use% Mounted on\n"
                    f"/dev/lxc-root   {c['disk']:>3}G  {used_g:>4}G  "
                    f"{round(c['disk']-used_g,1):>4}G  {int(used_g/c['disk']*100):>3}% /")
        if low == "ps":
            return ("  PID TTY          TIME CMD\n    1 ?        00:00:01 systemd\n"
                    "  142 ?        00:00:04 sshd")
        if low.startswith("top"):
            cpu = live["cpu_pct"] / max(c["cpu"], 1)
            return (f"top - {time.strftime('%H:%M:%S')} up {self._fmt_upt(live['uptime_s'])}\n"
                    f"%Cpu(s): {cpu:5.1f} us,  1.8 sy, {100-cpu-1.8:5.1f} id\n"
                    f"MiB Mem : {c['mem']:.1f} total, {live['mem_used_mb']:.1f} used")
        if low.startswith("cat /etc/os-release"):
            pretty = PRETTY_OS.get(tpl, tpl)
            ver = tpl.split("-", 1)[-1].replace("-", ".")
            return (f'NAME="{pretty.split()[0]}"\nVERSION="{ver}"\n'
                    f'ID={tpl.split("-")[0]}\nPRETTY_NAME="{pretty}"\n')
        if low.startswith(("ip a", "ip addr", "ifconfig")):
            import random as r
            return (f"1: lo: <LOOPBACK,UP> mtu 65536\n    inet 127.0.0.1/8 scope host lo\n"
                    f"2: eth0: <BROADCAST,MULTICAST,UP>\n    inet {c['ip'] or '10.0.0.x'}/24 scope global eth0\n"
                    f"    link/ether 00:16:3e:{r.randint(16,255):02x}:aa:{r.randint(16,255):02x}")
        if low.startswith("ping"):
            host = cmd.split()[-1] if len(cmd.split()) > 1 else "example.com"
            lines = [f"PING {host} (93.184.216.34) 56(84) bytes of data."]
            for i in range(1, 5):
                lines.append(f"64 bytes from {host}: icmp_seq={i} ttl=56 time={random.uniform(8,26):.1f} ms")
            lines += ["", "--- statistics ---", "4 transmitted, 4 received, 0% loss"]
            return "\n".join(lines)
        if low == "neofetch":
            return ("       .--.        root@" + name +
                    "\n      |o_o |       -------------------" +
                    "\n      |:_/ |       OS: " + PRETTY_OS.get(tpl, tpl) +
                    "\n     //   \\ \\      Kernel: 5.15.0-91-generic" +
                    "\n    (|     | )     Uptime: " + self._fmt_upt(live["uptime_s"]) +
                    "\n   /'\\_   _/`\\     CPU: " + str(c["cpu"]) + " vCPU | Memory: " +
                    str(live["mem_used_mb"]) + "/" + str(c["mem"]) + " MiB")
        return f"-bash: {cmd.split()[0]}: command not found"


# ════════════════════ SSH 真实节点操作 ════════════════════
class SshOps:
    """所有方法在失败时抛 RuntimeError(含远端输出尾部)"""

    @staticmethod
    def _run(node_row, cmd, timeout=60):
        rc, out = nodes_mod.run_cmd(node_row, cmd, timeout=timeout)
        return rc, out

    @classmethod
    def start(cls, node_row, c):
        rc, out = cls._run(node_row, f"lxc-start -n {shlex.quote(c['name'])}")
        if rc: raise RuntimeError(out[-300:] or "lxc-start 失败")

    @classmethod
    def stop(cls, node_row, c):
        rc, out = cls._run(node_row, f"lxc-stop -n {shlex.quote(c['name'])}", timeout=90)
        if rc and "not running" not in out.lower(): raise RuntimeError(out[-300:] or "lxc-stop 失败")

    @classmethod
    def restart(cls, node_row, c):
        rc, out = cls._run(node_row, f"lxc-stop -r -n {shlex.quote(c['name'])}", timeout=120)
        if rc: raise RuntimeError(out[-300:] or "lxc-stop -r 失败")

    @classmethod
    def create(cls, node_row, c):
        key = c["template"]
        distro, release = TEMPLATE_IMAGE_MAP.get(key, (None, None))
        if not distro:
            raise RuntimeError(f"模板 {key} 缺少镜像映射")
        cmd = (f"lxc-create -n {shlex.quote(c['name'])} -t download -- "
               f"-d {distro} -r {release} -a amd64")
        rc, out = cls._run(node_row, cmd, timeout=1200)
        if rc:
            cls._run(node_row, f"lxc-destroy -nf {shlex.quote(c['name'])}", timeout=60)
            raise RuntimeError((out[-400:]) or "lxc-create 失败")

    @classmethod
    def delete(cls, node_row, c):
        cls._run(node_row, f"lxc-destroy -f {shlex.quote(c['name'])}", timeout=90)


class AgentOps:
    """通过 Agent 命令通道执行 lxc-* 操作"""

    @staticmethod
    def _exec(node_row, script, timeout=120):
        from . import agent as agent_mod
        if not agent_mod.is_online(node_row["id"]):
            raise RuntimeError("Agent 离线")
        cid = agent_mod.queue_exec(node_row["id"], script, timeout=timeout)
        res = agent_mod.wait_result(cid, timeout + 30)
        if res is None:
            raise RuntimeError("Agent 执行超时")
        return res["rc"], res["out"]

    @classmethod
    def start(cls, node_row, c):
        rc, out = cls._exec(node_row, f"lxc-start -n {shlex.quote(c['name'])}")
        if rc: raise RuntimeError(out[-300:] or "lxc-start 失败")

    @classmethod
    def stop(cls, node_row, c):
        rc, out = cls._exec(node_row, f"lxc-stop -n {shlex.quote(c['name'])}", 90)
        if rc and "not running" not in out.lower(): raise RuntimeError(out[-300:])

    @classmethod
    def restart(cls, node_row, c):
        rc, out = cls._exec(node_row, f"lxc-stop -r -n {shlex.quote(c['name'])}", 120)
        if rc: raise RuntimeError(out[-300:])

    @classmethod
    def create(cls, node_row, c):
        key = c["template"]
        distro, release = TEMPLATE_IMAGE_MAP.get(key, (None, None))
        if not distro:
            raise RuntimeError(f"模板 {key} 缺少镜像映射")
        script = (f"lxc-create -n {shlex.quote(c['name'])} -t download -- "
                  f"-d {distro} -r {release} -a amd64")
        rc, out = cls._exec(node_row, script, 1200)
        if rc:
            cls._exec(node_row, f"lxc-destroy -nf {shlex.quote(c['name'])}", 60)
            raise RuntimeError(out[-400:] or "lxc-create 失败")

    @classmethod
    def delete(cls, node_row, c):
        cls._exec(node_row, f"lxc-destroy -f {shlex.quote(c['name'])}", 90)


def ops_for(node_row):
    """统一入口: 按 kind 返回操作器"""
    if node_row["kind"] == "demo":
        from . import monitor
        return monitor.demo_runtime(node_row["id"])
    if node_row["kind"] == "agent":
        return AgentOps()
    return SshOps()
