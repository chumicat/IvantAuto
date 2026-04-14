"""GUI watcher and OTP injector — handles both credential and TOTP dialogs."""

import logging
import time

import win32con
import win32gui

from .totp import TOTPGenerator
from .utils import is_process_running

log = logging.getLogger(__name__)

# Known Ivanti dialog title substrings
DEFAULT_OTP_TITLES = [
    "Connect to:",
    "Ivanti Secure Access",
    "Pulse Secure",
    "Secondary Authentication",
    "Enter Passcode",
    "Authentication",
    "Sign In",
]

# Win32 messages — work regardless of desktop lock state
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5

# Dialog auto_ids (confirmed via diag)
# Credential dialog (username/password)
_CRED_USERNAME_ID = "10111"
_CRED_PASSWORD_ID = "10115"
# TOTP dialog (secondary auth)
_TOTP_USERNAME_ID = "10113"
_TOTP_FIELD_ID = "10137"
# Shared
_CONNECT_BTN_ID = "10201"


class InjectionError(Exception):
    pass


# ---------------------------------------------------------------------------
# Dialog detection
# ---------------------------------------------------------------------------

def _find_hwnd_by_title(title_substrings: list[str]) -> int | None:
    """Find a visible window whose title contains any of the substrings."""
    found = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            for substr in title_substrings:
                if substr.lower() in title.lower():
                    found.append(hwnd)
                    break

    win32gui.EnumWindows(callback, None)
    return found[0] if found else None


def _uia_child_exists(dialog_hwnd: int, auto_id: str) -> int | None:
    """Check if a UIA child with the given auto_id exists. Returns its hwnd or None."""
    try:
        from pywinauto import Application
        app = Application(backend="uia").connect(handle=dialog_hwnd)
        dlg = app.window(handle=dialog_hwnd)
        child = dlg.child_window(auto_id=auto_id, control_type="Edit")
        if child.exists(timeout=1):
            return child.handle
    except Exception:
        pass
    return None


def _find_child_by_title(parent_hwnd: int, target_title: str) -> int | None:
    """Find a child window whose title contains the target string."""
    found = []

    def callback(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if target_title.lower() in title.lower():
            found.append(hwnd)

    win32gui.EnumChildWindows(parent_hwnd, callback, None)
    return found[0] if found else None


def detect_dialog_type(dialog_hwnd: int) -> str:
    """Detect whether this is a 'credential' or 'totp' dialog.

    Both have the same window title 'Connect to: ...'.
    Credential dialog has auto_id=10111 (User Name) + 10115 (Password).
    TOTP dialog has auto_id=10137 (secondary token).
    """
    if _uia_child_exists(dialog_hwnd, _TOTP_FIELD_ID):
        return "totp"
    if _uia_child_exists(dialog_hwnd, _CRED_PASSWORD_ID):
        return "credential"
    # Fallback: check via win32gui child titles
    if _find_child_by_title(dialog_hwnd, "secondary"):
        return "totp"
    if _find_child_by_title(dialog_hwnd, "&Password:"):
        return "credential"
    return "unknown"


# ---------------------------------------------------------------------------
# SendMessage helpers (work on locked desktops)
# ---------------------------------------------------------------------------

def _get_edit_hwnd(dialog_hwnd: int, auto_id: str) -> int | None:
    """Find an Edit control by UIA auto_id, falling back to win32gui."""
    try:
        from pywinauto import Application
        app = Application(backend="uia").connect(handle=dialog_hwnd)
        dlg = app.window(handle=dialog_hwnd)
        edit = dlg.child_window(auto_id=auto_id, control_type="Edit")
        h = edit.handle
        if h:
            return h
    except Exception as e:
        log.debug(f"UIA lookup for auto_id={auto_id} failed: {e}")
    return None


def _get_btn_hwnd(dialog_hwnd: int, auto_id: str = _CONNECT_BTN_ID) -> int | None:
    """Find a Button by UIA auto_id, falling back to win32gui title search."""
    try:
        from pywinauto import Application
        app = Application(backend="uia").connect(handle=dialog_hwnd)
        dlg = app.window(handle=dialog_hwnd)
        btn = dlg.child_window(auto_id=auto_id, control_type="Button")
        h = btn.handle
        if h:
            return h
    except Exception as e:
        log.debug(f"UIA button lookup for auto_id={auto_id} failed: {e}")
    h = _find_child_by_title(dialog_hwnd, "&Connect")
    return h


def _set_edit_text(edit_hwnd: int, text: str) -> bool:
    """Set text on an Edit control via WM_SETTEXT, falling back to WM_CHAR."""
    win32gui.SendMessage(edit_hwnd, win32con.WM_SETFOCUS, 0, 0)
    time.sleep(0.1)

    # Clear
    win32gui.SendMessage(edit_hwnd, WM_SETTEXT, 0, "")
    time.sleep(0.1)

    # Try WM_SETTEXT
    win32gui.SendMessage(edit_hwnd, WM_SETTEXT, 0, text)

    # Verify
    length = win32gui.SendMessage(edit_hwnd, WM_GETTEXTLENGTH, 0, 0)
    if length != len(text):
        log.debug(f"WM_SETTEXT got {length} chars, expected {len(text)}, using WM_CHAR ...")
        win32gui.SendMessage(edit_hwnd, WM_SETTEXT, 0, "")
        for ch in text:
            win32gui.SendMessage(edit_hwnd, win32con.WM_CHAR, ord(ch), 0)
            time.sleep(0.02)
        length = win32gui.SendMessage(edit_hwnd, WM_GETTEXTLENGTH, 0, 0)

    return length == len(text)


def _click_button(btn_hwnd: int) -> None:
    """Click a button via BM_CLICK."""
    win32gui.SendMessage(btn_hwnd, BM_CLICK, 0, 0)


# ---------------------------------------------------------------------------
# Credential dialog handler
# ---------------------------------------------------------------------------

def fill_credential_dialog(dialog_hwnd: int, username: str, password: str) -> bool:
    """Fill in the username/password dialog and click Connect."""
    log.info("Detected CREDENTIAL dialog — filling username + password ...")

    user_hwnd = _get_edit_hwnd(dialog_hwnd, _CRED_USERNAME_ID)
    pass_hwnd = _get_edit_hwnd(dialog_hwnd, _CRED_PASSWORD_ID)
    btn_hwnd = _get_btn_hwnd(dialog_hwnd)

    if not user_hwnd or not pass_hwnd or not btn_hwnd:
        log.error(f"Could not find credential fields (user={user_hwnd}, pass={pass_hwnd}, btn={btn_hwnd})")
        return False

    _set_edit_text(user_hwnd, username)
    _set_edit_text(pass_hwnd, password)
    time.sleep(0.2)
    _click_button(btn_hwnd)
    log.info("Credential dialog submitted.")
    return True


# ---------------------------------------------------------------------------
# TOTP dialog handler
# ---------------------------------------------------------------------------

def fill_totp_dialog(dialog_hwnd: int, code: str) -> bool:
    """Fill in the TOTP dialog and click Connect."""
    log.info("Detected TOTP dialog — filling TOTP code ...")

    edit_hwnd = _get_edit_hwnd(dialog_hwnd, _TOTP_FIELD_ID)
    btn_hwnd = _get_btn_hwnd(dialog_hwnd)

    if not edit_hwnd or not btn_hwnd:
        log.error(f"Could not find TOTP fields (edit={edit_hwnd}, btn={btn_hwnd})")
        return False

    ok = _set_edit_text(edit_hwnd, code)
    if not ok:
        log.warning("TOTP text may not have been set correctly.")

    time.sleep(0.2)
    _click_button(btn_hwnd)
    log.info(f"TOTP injected via SendMessage ({code[:2]}****).")
    return True


# ---------------------------------------------------------------------------
# Strategy A — Loop-based
# ---------------------------------------------------------------------------

class LoopInjector:
    def __init__(self, custom_titles: list[str] | None = None):
        self.titles = custom_titles if custom_titles else DEFAULT_OTP_TITLES

    def inject(self, totp_gen: TOTPGenerator, timeout: int = 120,
               username: str = "", password: str = "") -> bool:
        log.info(f"Loop injector: waiting up to {timeout}s ...")
        time.sleep(3)

        deadline = time.time() + timeout
        last_code = None
        cred_filled = False

        while time.time() < deadline:
            if not is_process_running("pulselauncher.exe"):
                log.info("pulselauncher.exe exited.")
                break

            hwnd = _find_hwnd_by_title(self.titles)
            if not hwnd:
                time.sleep(1)
                continue

            dtype = detect_dialog_type(hwnd)

            if dtype == "credential" and not cred_filled:
                fill_credential_dialog(hwnd, username, password)
                cred_filled = True
                time.sleep(3)
                continue

            if dtype == "totp":
                code = totp_gen.current_code()
                if code != last_code:
                    remaining = totp_gen.seconds_remaining()
                    if remaining < 5:
                        time.sleep(remaining + 1)
                        code = totp_gen.current_code()
                    if fill_totp_dialog(hwnd, code):
                        last_code = code
                        return True

            time.sleep(1)

        return False


# ---------------------------------------------------------------------------
# Strategy B — Window watcher (handles both dialog stages)
# ---------------------------------------------------------------------------

class WindowWatcher:
    def __init__(self, custom_titles: list[str] | None = None):
        self.titles = custom_titles if custom_titles else DEFAULT_OTP_TITLES

    def _wait_for_hwnd(self, timeout: int) -> int | None:
        log.info(f"Window watcher: scanning for dialog (timeout {timeout}s) ...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            hwnd = _find_hwnd_by_title(self.titles)
            if hwnd:
                title = win32gui.GetWindowText(hwnd)
                log.info(f"Found dialog: '{title}' (hwnd={hwnd:#x})")
                return hwnd
            time.sleep(0.5)
        return None

    def inject(self, totp_gen: TOTPGenerator, timeout: int = 60,
               username: str = "", password: str = "") -> bool:
        hwnd = self._wait_for_hwnd(timeout)
        if hwnd is None:
            log.warning("No dialog found within timeout.")
            return False

        dtype = detect_dialog_type(hwnd)
        log.info(f"Dialog type: {dtype}")

        # Stage 1: credential dialog — fill username/password, then wait for TOTP
        if dtype == "credential":
            if not fill_credential_dialog(hwnd, username, password):
                return False

            # Wait for the TOTP dialog to appear.
            # Ivanti may reuse the same hwnd (controls swap) or create a new window.
            # Poll until detect_dialog_type reports "totp" on whichever hwnd we find.
            log.info("Waiting for TOTP dialog after credential submission ...")
            time.sleep(3)
            totp_deadline = time.time() + timeout
            hwnd2 = None
            while time.time() < totp_deadline:
                candidate = _find_hwnd_by_title(self.titles)
                if candidate:
                    dtype2 = detect_dialog_type(candidate)
                    log.debug(f"Post-credential dialog check: hwnd={candidate:#x}, type={dtype2}")
                    if dtype2 == "totp":
                        hwnd2 = candidate
                        break
                time.sleep(1)

            if hwnd2 is None:
                log.warning("TOTP dialog did not appear after credential submission.")
                return False

            log.info(f"TOTP dialog found (hwnd={hwnd2:#x}).")
            hwnd = hwnd2

        # Stage 2: TOTP dialog
        if dtype == "totp" or dtype == "credential":
            remaining = totp_gen.seconds_remaining()
            if remaining < 5:
                log.debug(f"Code expires in {remaining}s, waiting ...")
                time.sleep(remaining + 1)

            code = totp_gen.current_code()
            return fill_totp_dialog(hwnd, code)

        log.warning(f"Unknown dialog type: {dtype}")
        return False


def get_injector(strategy: str, custom_titles: list[str] | None = None):
    if strategy == "loop":
        return LoopInjector(custom_titles=custom_titles)
    elif strategy == "window":
        return WindowWatcher(custom_titles=custom_titles)
    else:
        raise ValueError(f"Unknown injection strategy: {strategy}")
