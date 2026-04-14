# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- **Python venv:** always use `.venv\Scripts\python` — never the system Python
- **Run the CLI:** `.venv\Scripts\python -m ivantauto <command>`
- **Install deps:** `.venv\Scripts\pip install -r requirements.txt`

## Common Commands

```bat
.venv\Scripts\python -m ivantauto --help
.venv\Scripts\python -m ivantauto -v connect       # one-shot connect (verbose)
.venv\Scripts\python -m ivantauto -v disconnect    # stop VPN
.venv\Scripts\python -m ivantauto -v status        # ping test_domain
.venv\Scripts\python -m ivantauto daemon           # persistent 55-min reconnect loop
.venv\Scripts\python -m ivantauto setup            # store credentials in Windows Credential Manager
.venv\Scripts\python -m ivantauto debug-windows    # list visible window titles (for OTP dialog tuning)
```

## Architecture

Single-package CLI (`ivantauto/`) wired together in `__main__.py`:

| Module | Responsibility |
|---|---|
| `config.py` | Load `config.ini`, auto-detect `pulselauncher.exe` and `jamCommand.exe` paths |
| `vault.py` | Read/write secrets via Windows Credential Manager (`keyring`) |
| `totp.py` | Generate TOTP codes from secret (`pyotp`) |
| `launcher.py` | Launch `pulselauncher.exe`, disconnect via `sc stop PulseSecureService`, ping connectivity |
| `gui_handler.py` | Detect and fill the TOTP dialog — two strategies (see below) |
| `daemon.py` | Reconnect loop with `before/after_reconnect` hook stubs for future MCP integration |

## GUI Automation — Critical Facts

The Ivanti TOTP dialog is a native Win32 window (`JamShadowClass`) that does **not** expose controls cleanly via `Desktop(backend="uia").windows()`. The correct approach (already implemented):

1. Find the window via `win32gui.EnumWindows` by title substring
2. Connect pywinauto to it by hwnd: `Application(backend="uia").connect(handle=hwnd)`
3. Inject into `auto_id="10137"` (TOTP Edit field), click `auto_id="10201"` (Connect button)

**Two injection strategies** (set via `config.ini` `injection_strategy`):
- `window` (default) — pywinauto UIA by hwnd, with `pyautogui` fallback
- `loop` — polls `pulselauncher.exe` process presence, types into focused window

**OTP dialog title:** `"Connect to: SystexCloud"` — `"Connect to:"` is in the default title list.

## Disconnect

Only `sc stop PulseSecureService` actually drops the VPN tunnel. `taskkill /F Pulse.exe` and `jamCommand.exe -stop` only close the UI — the tunnel persists.

## Daemon Mode Constraint

The daemon **must run in an interactive Windows desktop session**. Ivanti's TOTP dialog is a GUI window that only renders when a user is logged in. Running as a Windows service or in a detached session will cause the window watcher to time out silently.

## Credentials

No secrets in `config.ini`. Credentials are stored in Windows Credential Manager under service name `IvantAuto`. Run `ivantauto setup` to store; `ivantauto clear-creds` to remove.

## After Service Restart

When `PulseSecureService` is stopped and restarted, the Ivanti server may reuse a cached auth session and connect without showing the TOTP dialog. `do_connect()` in `daemon.py` handles this: if no OTP dialog appears, it checks connectivity directly and treats a successful ping as a successful connect.
