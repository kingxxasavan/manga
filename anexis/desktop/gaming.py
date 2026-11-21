"""Is a game in front? Game mode for JARVIS.

While a full screen program (a game, or a full screen video) is in front,
JARVIS only answers when it hears its name, so game sounds and voices cannot
set it off, and Anexis keeps its check ins to itself until the game is
closed. Talking to it ("Jarvis, ...") works the whole time.

Windows only. Two signs, either is enough: Windows itself says a Direct3D
program has the screen (exclusive full screen), or the window in front
covers its whole monitor (borderless "windowed full screen", which is how
most games run now). The desktop and Anexis itself never count.
"""

from __future__ import annotations

import psutil

from anexis.platform import IS_WINDOWS

# Full screen windows that are not games.
NOT_GAMES = {
    "explorer.exe", "anexis.exe", "electron.exe", "lockapp.exe", "searchhost.exe", "searchapp.exe",
    "shellexperiencehost.exe", "startmenuexperiencehost.exe", "textinputhost.exe", "screenclippinghost.exe",
}
QUNS_RUNNING_D3D_FULL_SCREEN = 3


def full_screen_app(name: str, window: tuple, monitor: tuple, d3d: bool = False) -> str:
    """`name` when that program has the whole screen, else "". Rectangles are
    (left, top, right, bottom)."""
    if not name or name.lower() in NOT_GAMES:
        return ""
    left, top, right, bottom = window
    m_left, m_top, m_right, m_bottom = monitor
    covers = left <= m_left and top <= m_top and right >= m_right and bottom >= m_bottom
    return name if d3d or covers else ""


def game_in_front() -> str:
    """The program name of the full screen game in front, or ""."""
    if not IS_WINDOWS:
        return ""
    try:
        return _windows()
    except Exception:  # never worth breaking anything over
        return ""


def _windows() -> str:  # pragma: no cover - needs Windows
    import ctypes
    from ctypes import wintypes

    user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]

    window = user32.GetForegroundWindow()
    if not window:
        return ""
    rect = wintypes.RECT()
    if not user32.GetWindowRect(window, ctypes.byref(rect)):
        return ""
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(window, 2), ctypes.byref(info)):  # 2: the nearest monitor
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    try:
        name = psutil.Process(pid.value).name()
    except psutil.Error:
        return ""
    state = ctypes.c_int(0)
    d3d = shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0 and state.value == QUNS_RUNNING_D3D_FULL_SCREEN
    m = info.rcMonitor
    return full_screen_app(name, (rect.left, rect.top, rect.right, rect.bottom), (m.left, m.top, m.right, m.bottom), d3d)
