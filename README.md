# IvantAuto

Automates connection to **Ivanti Secure Access Client** (formerly Pulse Secure) on Windows,
including automatic TOTP code injection. Designed for maintaining persistent VPN access to
lab environments (e.g. Ollama models) without manual reconnection every hour.

---

## How It Works

1. Launches `pulselauncher.exe` with your VPN credentials via CLI
2. Detects the TOTP dialog using `pywinauto` (UIA backend) or a process-poll fallback
3. Injects the current 6-digit TOTP code automatically
4. In **daemon mode**, monitors connectivity and reconnects automatically when the VPN drops

---

## Requirements

- Windows 10/11 (or Windows Server)
- Python 3.10+
- Ivanti Secure Access Client installed (provides `pulselauncher.exe`)
- Your TOTP secret (see [Extracting Your TOTP Secret](#extracting-your-totp-secret) below)

---

## Installation

### Option A — pip + git (no clone needed)

```bat
pip install git+https://github.com/chumicat/IvantAuto.git
```

This installs the `ivantauto` CLI command directly. You still need to create a `config.ini` (see Quick Start below).

### Option B — clone and install (editable)

```bat
git clone https://github.com/chumicat/IvantAuto.git
cd IvantAuto

python -m venv .venv
.venv\Scripts\pip install -e .
```

---

## Quick Start

### Step 1 — Copy and fill in config

```bat
copy config.ini.template config.ini
```

Edit `config.ini`:

```ini
[host]
url = vpn.yourcompany.com                     ← copy exactly what the Ivanti client UI shows (no http/https unless the UI shows it)
test_domain = internal.yourcompany.com        ← optional: internal host to ping for status checks

[auth]
username = john                               ← your VPN username
realm = Users                                 ← your VPN realm (see "Finding Your Realm" below)

[start]
pulselauncher_path =                          ← leave blank to auto-detect

[options]
injection_strategy = window                   ← "window" (default) or "loop" (fallback)
otp_dialog_timeout = 60
reconnect_interval_min = 55                   ← used by interval mode and force_reconnect safety net

[daemon]
daemon_mode = heartbeat                       ← "heartbeat" (reactive) or "interval" (fixed timer)
heartbeat_interval_sec = 5                    ← seconds between pings (heartbeat mode)
heartbeat_fail_threshold = 3                  ← consecutive failures before reconnect
force_reconnect = false                       ← force periodic reconnect even if VPN is healthy
```

### Step 2 — Store credentials securely

```bat
.venv\Scripts\python -m ivantauto setup
```

You will be prompted for:

| Prompt | What to enter |
|---|---|
| `VPN password:` | Your VPN login password |
| `TOTP secret:` | The **secret** value from your `otpauth://` URI (see below) |

Credentials are encrypted and stored in **Windows Credential Manager** (DPAPI-backed).
They are never written to `config.ini` or any file on disk.

### Step 3 — Test a one-shot connection

```bat
.venv\Scripts\python -m ivantauto connect
```

To disconnect any existing session before connecting (recommended if a stale VPN or UI may be open):

```bat
.venv\Scripts\python -m ivantauto connect --clean-start
```

### Step 4 — Run the daemon

```bat
.venv\Scripts\python -m ivantauto daemon
```

The daemon has two modes:

#### Heartbeat mode (default)

Pings `test_domain` every 5 seconds. If 3 consecutive pings fail, it triggers a full reconnect (disconnect + clean UI + reconnect). This is reactive — it only reconnects when the VPN actually drops.

```bat
.venv\Scripts\python -m ivantauto daemon --mode heartbeat
```

If a reconnect fails, the daemon backs off exponentially (10s → 20s → ... up to 5 min between checks) and keeps retrying indefinitely. On successful reconnect, the poll interval resets to normal.

> **Requires `test_domain`** in `config.ini`. If not set, the daemon falls back to interval mode automatically.

#### Interval mode

The original fixed-timer approach: reconnect every N minutes regardless of connectivity status. Useful if you don't have a `test_domain` to ping.

```bat
.venv\Scripts\python -m ivantauto daemon --mode interval
```

#### Daemon flags

| Flag | Effect |
|---|---|
| `--clean-start` | Disconnect before the **first** connect cycle |
| `--force-reconnect` | Force a periodic disconnect+reconnect even if VPN appears healthy (heartbeat mode uses `reconnect_interval_min` as the interval; interval mode disconnects before every cycle) |
| `--mode {heartbeat,interval}` | Override daemon mode from config.ini |

Permanent config equivalents:

```ini
[options]
clean_start = true

[daemon]
daemon_mode = heartbeat
force_reconnect = true
; Heartbeat settings (only used in heartbeat mode)
heartbeat_interval_sec = 5
heartbeat_fail_threshold = 3
```

#### What happens during a reconnect?

Every reconnect (whether triggered by heartbeat failure, interval timer, or retry) performs:

1. **Full disconnect** — stops `PulseSecureService` (drops the VPN tunnel)
2. **Kill all Pulse\* processes** — removes `Pulse.exe`, `PulseSetupClient.exe`, etc. from the tray
3. **Restart service** — starts `PulseSecureService` fresh
4. **Launch `pulselauncher.exe`** — with credentials
5. **Fill dialogs** — handles credential dialog (username/password) then TOTP dialog automatically
6. **Verify** — pings `test_domain` to confirm the VPN is up

If the TOTP injection succeeds but the VPN doesn't come up, it retries up to `connect_max_retries` times (default: 2), with a full disconnect+cleanup between each retry.

---

## Finding Your Realm

The **realm** is the authentication domain name configured on the Ivanti gateway.
It may or may not appear as a dropdown on the login page.

### If there is a dropdown on the login page

The selected value is your realm — copy it exactly into `config.ini`.

### If there is no dropdown (hidden realm)

Use browser DevTools to capture it from the login request:

1. Open your VPN portal URL in a browser
2. Press **F12** → go to the **Network** tab
3. Enable **Preserve log** (checkbox near the top) so requests don't clear on redirect
4. Submit the login form normally
5. In the Network tab, find the request named **`login.cgi`** with status **200**
   (ignore the one with status 302 — that is the redirect after login)
6. Click it → open the **Payload** tab (Chrome) / **Request** tab (Firefox)
7. Under **Form Data**, find the field named `realm`

The value is your realm — spaces are allowed, copy it exactly.

**Example form data you might see:**
```
username=john&password=...&realm=Ldaps user&SubmitButton=Sign+In
```
→ realm is `Ldaps user`

---

## Extracting Your TOTP Secret

Your authenticator app exports TOTP accounts in this format:

```
otpauth://totp/<user>?secret=<SECRET>&issuer=<issuer>
```

**Example:**
```
otpauth://totp/john%40company.com?secret=JBSWY3DPEHPK3PXP&issuer=CompanyVPN
```

**What to extract:** the value after `secret=` up to the next `&` (or end of string).

In the example above: `JBSWY3DPEHPK3PXP`

This is the **base32 TOTP secret** — paste it at the `TOTP secret:` prompt during `ivantauto setup`.

> The `<user>` and `issuer=` parts are labels only — IvantAuto does not need them.

### How to get the otpauth:// URI from your app

| App | Method |
|---|---|
| **Google Authenticator** | Account → three-dot menu → Export accounts → scan QR with a decoder like [zxing.org/w/decode.jspx](https://zxing.org/w/decode.jspx) |
| **Authy** | Enable backups, use Authy desktop, or extract via [this guide](https://authy.com/blog/how-the-authy-two-factor-backups-work/) |
| **1Password / Bitwarden** | View the item — the TOTP secret is shown directly in the field |
| **Microsoft Authenticator** | Export to backup, or ask your IT team for the provisioning QR code |
| **Company-issued QR code** | Scan with a QR reader — the decoded text is the full `otpauth://` URI |

If you only have a QR code image, decode it at [zxing.org/w/decode.jspx](https://zxing.org/w/decode.jspx) to get the URI, then copy the `secret=` value.

---

## All Commands

```
.venv\Scripts\python -m ivantauto [command]
```

| Command | Description |
|---|---|
| `setup` | Store VPN password and TOTP secret in Windows Credential Manager |
| `connect` | One-shot: connect once and exit. `--clean-start` to disconnect first |
| `daemon` | Persistent daemon. `--mode heartbeat` (default, reactive) or `--mode interval` (fixed timer). `--clean-start` / `--force-reconnect` |
| `status` | Ping `test_domain` to check if VPN is up |
| `clear-creds` | Remove all stored credentials |
| `debug-windows` | List all visible window titles every 2s (use this to find the OTP dialog name) |

Global flags: `-v` (verbose/debug logging), `-c config.ini` (custom config path)

---

## Troubleshooting

### OTP dialog not detected

Run `debug-windows` while the Ivanti client is showing its TOTP prompt:

```bat
.venv\Scripts\python -m ivantauto debug-windows
```

Note the exact window title, then add it to `config.ini`:

```ini
[options]
otp_window_titles = My Custom Dialog Title
```

Multiple titles: comma-separated.

### Falls back to `loop` strategy

If `window` strategy can't find controls (Ivanti uses a non-standard UI renderer), switch to:

```ini
injection_strategy = loop
```

The loop strategy polls for `pulselauncher.exe` and types the TOTP into whatever has keyboard focus.

### Permission denied

Run your terminal as Administrator, or check that `pulselauncher.exe` is reachable at the detected path.

### pulselauncher.exe not found

Set the path explicitly in `config.ini`:

```ini
[start]
pulselauncher_path = C:\path\to\pulselauncher.exe
```

---

## Security Notes

- **Password exposure:** `pulselauncher.exe` receives the password as a CLI argument, which is briefly visible in Task Manager. This is a limitation of the Ivanti CLI design, not IvantAuto.
- **TOTP secret:** Stored in Windows Credential Manager (encrypted with your Windows login via DPAPI). Not written to any file.
- **config.ini:** Contains no secrets — only URL, username, and realm (non-sensitive).

---

## Future: MCP / Service Integration

`daemon.py` exposes hook points for notifying other services before/after reconnect:

```python
from ivantauto.daemon import on_before_reconnect, on_after_reconnect

on_before_reconnect(lambda: print("Pausing Ollama client..."))
on_after_reconnect(lambda: print("Resuming Ollama client..."))
```

Planned: integration with MCP tools (e.g. openclaw) so that 24/7 agents can pause gracefully
during reconnect and resume automatically. Not yet implemented.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
