"""Utility functions — ping, process detection, window helpers."""

import subprocess

import psutil


def is_host_reachable(hostname: str, timeout: int = 5) -> bool:
    """Ping a hostname to check reachability (VPN connectivity test)."""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout * 1000), hostname],
            capture_output=True,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return result.returncode == 0
    except Exception:
        return False


def is_process_running(name: str) -> bool:
    """Check if a process with the given name is currently running."""
    name_lower = name.lower()
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == name_lower:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def list_window_titles() -> list[str]:
    """List all visible window titles (for debugging OTP dialog detection)."""
    import win32gui

    titles = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                titles.append(title)

    win32gui.EnumWindows(callback, None)
    return titles
