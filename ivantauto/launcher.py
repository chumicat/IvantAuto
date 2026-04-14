"""VPN process launcher — wraps pulselauncher.exe subprocess."""

import logging
import subprocess
import time

from .config import Config
from .utils import is_host_reachable, is_process_running

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000


class LaunchError(Exception):
    pass


class VPNLauncher:
    def __init__(self, config: Config):
        self.config = config

    def is_already_connected(self) -> bool:
        """Check if VPN is already up by pinging the test domain."""
        if not self.config.test_domain:
            log.debug("No test_domain configured, skipping connectivity check.")
            return False
        return is_host_reachable(self.config.test_domain)

    def is_launcher_running(self) -> bool:
        """Check if pulselauncher.exe is currently running."""
        return is_process_running("pulselauncher.exe")

    def launch(self, password: str) -> subprocess.Popen:
        """Start pulselauncher.exe with credentials. Returns the Popen handle."""
        cfg = self.config
        args = [
            cfg.pulselauncher_path,
            "-url", cfg.vpn_url,
            "-u", cfg.username,
            "-p", password,
            "-r", cfg.realm,
        ]

        # Kill stale Pulse* processes before launching — leftover instances block
        # pulselauncher.exe from establishing a new connection via IPC.
        self._kill_all_pulse_processes()

        log.info("Launching pulselauncher.exe ...")
        try:
            proc = subprocess.Popen(
                args,
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except PermissionError:
            raise LaunchError(
                "Permission denied launching pulselauncher.exe. "
                "Try running IvantAuto as Administrator."
            )
        except FileNotFoundError:
            raise LaunchError(
                f"pulselauncher.exe not found at: {cfg.pulselauncher_path}"
            )

        return proc

    def disconnect(self) -> bool:
        """Disconnect the VPN: stop service, then kill all Pulse* processes."""
        log.info("Stopping PulseSecureService ...")
        result = subprocess.run(
            ["sc", "stop", "PulseSecureService"],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            log.info("PulseSecureService stopped — VPN disconnected.")
        elif result.returncode == 1062 or "not started" in (result.stdout + result.stderr).decode(errors="replace").lower():
            log.info("PulseSecureService was not running (already disconnected).")
        else:
            out = (result.stdout + result.stderr).decode(errors="replace").strip()
            log.error(f"sc stop failed (rc={result.returncode}): {out}")
            return False

        # Kill ALL Pulse* processes (Pulse.exe, PulseSetupClient.exe, etc.)
        # Leftover UI/setup processes hold stale state and block fresh connections.
        self._kill_all_pulse_processes()
        return True

    def _kill_all_pulse_processes(self) -> None:
        """Force-kill all Pulse* processes except PulseSecureService."""
        import psutil
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                name = proc.info["name"] or ""
                if name.lower().startswith("pulse") and name.lower() != "pulsesecureservice.exe":
                    proc.kill()
                    log.info(f"Killed {name} (pid={proc.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def ensure_service_running(self) -> bool:
        """Start PulseSecureService if it is stopped (needed before connecting)."""
        result = subprocess.run(
            ["sc", "start", "PulseSecureService"],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
            timeout=30,
        )
        # rc=1056 means already running
        if result.returncode in (0, 1056):
            return True
        out = (result.stdout + result.stderr).decode(errors="replace").strip()
        log.warning(f"sc start PulseSecureService: rc={result.returncode} {out}")
        return False

    def wait_for_connection(self, timeout: int = 30) -> bool:
        """After OTP injection, wait for VPN to come up."""
        if not self.config.test_domain:
            log.info("No test_domain — assuming connection succeeded.")
            return True

        log.info(f"Waiting up to {timeout}s for VPN connectivity ...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_host_reachable(self.config.test_domain, timeout=3):
                return True
            time.sleep(2)
        return False
