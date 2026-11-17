"""Live numbers about this machine for the deck's system panel."""

from __future__ import annotations

import platform as host_platform
import shutil
import socket
import subprocess
import time

import psutil

_last_net: tuple[float, int, int] | None = None
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
        "cores": psutil.cpu_percent(interval=None, percpu=True),
        "memory": {"used": memory.total - memory.available, "total": memory.total, "percent": memory.percent},
        "swap": {"used": swap.used, "total": swap.total},
        "disks": _disks(),
        "net": _net(),
        "gpus": _gpus(),
        "battery": {"percent": battery.percent, "plugged": battery.power_plugged} if battery else None,
        "uptime": round(time.time() - psutil.boot_time()),
        "processes": _top(),
        "process_count": len(_procs),
    }
