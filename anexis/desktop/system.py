"""Live numbers about this machine for the deck's system panel."""

from __future__ import annotations

import platform as host_platform
import shutil
import socket
import subprocess
import time

import psutil

_last_net: tuple[float, int, int] | None = None
_cpu_name = ""
_link: tuple[float, dict] = (0.0, {})
_gpu: tuple[float, list[dict]] = (0.0, [])
_gpu_missing = False
_procs: dict[int, psutil.Process] = {}
psutil.cpu_percent(interval=None)  # the first reading is always 0, take it now


def _net() -> dict:
    """Bytes per second up and down since the last time this was asked."""
    global _last_net
    now, counters = time.monotonic(), psutil.net_io_counters()
    up = down = 0.0
    if _last_net and now > _last_net[0]:
        span = now - _last_net[0]
        up = max(0, counters.bytes_sent - _last_net[1]) / span
        down = max(0, counters.bytes_recv - _last_net[2]) / span
    _last_net = (now, counters.bytes_sent, counters.bytes_recv)
    return {"up": round(up), "down": round(down), "sent": counters.bytes_sent, "received": counters.bytes_recv}


def cpu_name() -> str:
    """What the processor is called, read once."""
    global _cpu_name
    if _cpu_name:
        return _cpu_name
    name = ""
    try:
        if host_platform.system() == "Windows":
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                name = str(winreg.QueryValueEx(key, "ProcessorNameString")[0])
        else:
            with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
                name = next((line.split(":", 1)[1] for line in f if line.lower().startswith("model name")), "")
    except (OSError, ImportError, StopIteration):
        name = ""
    _cpu_name = " ".join((name or host_platform.processor() or host_platform.machine() or "unknown").split())
    return _cpu_name


def _link_state() -> dict:
    """Which network link this machine talks through and its address on it.
    Nothing is sent anywhere: connecting a UDP socket only picks a route."""
    global _link
    if time.monotonic() - _link[0] < 10 and _link[1]:
        return _link[1]
    address = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            address = probe.getsockname()[0]
    except OSError:
        address = ""
    name = ""
    try:
        for iface, addrs in psutil.net_if_addrs().items():
            if any(a.address == address for a in addrs):
                name = iface
                break
    except OSError:
        pass
    state = {"online": bool(address) and not address.startswith("127."), "ip": address or "none", "iface": name or "none"}
    _link = (time.monotonic(), state)
    return state


def _disks() -> list[dict]:
    out, seen = [], set()
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen or part.fstype in ("squashfs", "tmpfs", "devtmpfs", "overlay"):
            continue
        seen.add(part.mountpoint)
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:  # an empty card reader or a drive that is not ready
            continue
        out.append({"mount": part.mountpoint, "used": usage.used, "total": usage.total, "percent": usage.percent})
    if not out:
        usage = psutil.disk_usage("/")
        out.append({"mount": "/", "used": usage.used, "total": usage.total, "percent": usage.percent})
    return out[:6]


def _gpus() -> list[dict]:
    """Nvidia cards, asked at most every five seconds. No card, no entry."""
    global _gpu, _gpu_missing
    if _gpu_missing:
        return []
    if time.monotonic() - _gpu[0] < 5:
        return _gpu[1]
    smi = shutil.which("nvidia-smi")
    if not smi:
        _gpu_missing = True
        return []
    cards = []
    try:
        out = subprocess.run(
            [smi, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        for line in out.strip().splitlines():
            name, load, used, total, temp = (part.strip() for part in line.split(","))
            cards.append({"name": name, "percent": float(load), "used": float(used) * 1024**2,
                          "total": float(total) * 1024**2, "temp": float(temp)})
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    _gpu = (time.monotonic(), cards)
    return cards


def _top(n: int = 8) -> list[dict]:
    """The busiest programs. Process objects are kept between calls, because a
    CPU reading is only meaningful against the same object's previous one."""
    rows, alive = [], set()
    cores = psutil.cpu_count() or 1
    for proc in psutil.process_iter(["pid", "name"]):
        pid = proc.info["pid"]
        alive.add(pid)
        known = _procs.setdefault(pid, proc)
        try:
            with known.oneshot():
                rows.append({
                    "pid": pid, "name": known.name() or "?",
                    "cpu": round(known.cpu_percent(None) / cores, 1),
                    "memory": known.memory_info().rss,
                })
        except psutil.Error:
            continue
    for pid in set(_procs) - alive:
        del _procs[pid]
    rows = [r for r in rows if r["name"] not in ("System Idle Process", "")]
    return sorted(rows, key=lambda r: (-r["cpu"], -r["memory"]))[:n]


def stats() -> dict:
    memory, swap = psutil.virtual_memory(), psutil.swap_memory()
    battery = getattr(psutil, "sensors_battery", lambda: None)()
    return {
        "host": socket.gethostname(),
        "os": f"{host_platform.system()} {host_platform.release()}",
        "cpu": psutil.cpu_percent(interval=None),
        "cpu_name": cpu_name(),
        "link": _link_state(),
        "cores": psutil.cpu_percent(interval=None, percpu=True),
        # used: programs. cached: held by the system but given back on demand. free: nothing in it.
        "memory": {"used": memory.total - memory.available, "total": memory.total, "percent": memory.percent,
                   "cached": max(0, memory.available - memory.free), "free": memory.free},
        "swap": {"used": swap.used, "total": swap.total},
        "disks": _disks(),
        "net": _net(),
        "gpus": _gpus(),
        "battery": {"percent": battery.percent, "plugged": battery.power_plugged} if battery else None,
        "uptime": round(time.time() - psutil.boot_time()),
        "processes": _top(),
        "process_count": len(_procs),
    }
