"""Daemon — persistent reconnect loop on a configurable timer."""

import logging
import time
from datetime import datetime, timedelta
from typing import Callable

from .config import Config
from .gui_handler import get_injector
from .launcher import VPNLauncher
from .totp import TOTPGenerator
from .utils import is_host_reachable
from .vault import get_password, get_totp_secret

log = logging.getLogger(__name__)


# Hook points for future MCP/service integration.
# Replace these with real callbacks when the notification layer is ready.
_before_reconnect_hooks: list[Callable] = []
_after_reconnect_hooks: list[Callable] = []


def on_before_reconnect(fn: Callable) -> None:
    """Register a callback to run before each reconnect."""
    _before_reconnect_hooks.append(fn)


def on_after_reconnect(fn: Callable) -> None:
    """Register a callback to run after each reconnect."""
    _after_reconnect_hooks.append(fn)


def _fire_hooks(hooks: list[Callable], label: str) -> None:
    for fn in hooks:
        try:
            fn()
        except Exception as e:
            log.warning(f"Hook {label}/{fn.__name__} failed: {e}")


def do_connect(config: Config, disconnect_first: bool = False) -> bool:
    """Execute a single connect cycle: launch VPN, inject TOTP, verify."""
    launcher = VPNLauncher(config)

    if disconnect_first:
        log.info("Clean-start: disconnecting before connecting.")
        launcher.disconnect()
        time.sleep(3)

    # Already connected?
    if launcher.is_already_connected():
        log.info("VPN is already connected.")
        return True

    # Ensure the service is running before attempting to connect
    launcher.ensure_service_running()

    # Retrieve credentials
    password = get_password(config.username)
    totp_secret = get_totp_secret(config.username)
    totp_gen = TOTPGenerator(totp_secret)

    injector = get_injector(config.injection_strategy, config.otp_window_titles or None)
    max_attempts = config.connect_max_retries + 1

    for attempt in range(max_attempts):
        if attempt > 0:
            log.warning(f"Retrying connect (attempt {attempt + 1}/{max_attempts}) ...")
            # Full disconnect before retry: stop service + kill UI
            launcher.disconnect()
            time.sleep(3)
            launcher.ensure_service_running()

        # Launch (also kills stale Pulse.exe UI)
        launcher.launch(password)

        # Handle both credential dialog and TOTP dialog
        injected = injector.inject(
            totp_gen, timeout=config.otp_dialog_timeout,
            username=config.username, password=password,
        )

        if not injected:
            log.info("No OTP dialog appeared — checking if VPN connected without it ...")
            if launcher.wait_for_connection(timeout=15):
                log.info("VPN connected (server skipped TOTP — cached session).")
                return True
            log.error("Failed to inject TOTP and VPN did not connect.")
            return False

        # Verify connectivity
        connected = launcher.wait_for_connection(timeout=config.connect_verify_timeout)
        if connected:
            log.info("VPN connected successfully.")
            return True

        log.warning(
            f"VPN not connected after attempt {attempt + 1}/{max_attempts} "
            f"— TOTP may have been rejected by server."
        )

    log.error(f"VPN connection failed after {max_attempts} attempt(s).")
    return False


def run_daemon(
    config: Config,
    force_reconnect: bool = False,
    clean_start: bool = False,
    mode_override: str | None = None,
) -> None:
    """Main daemon entry point — dispatches to heartbeat or interval loop."""
    mode = mode_override or config.daemon_mode

    if mode == "heartbeat" and not config.test_domain:
        log.warning("No test_domain configured — heartbeat mode requires it. Falling back to interval mode.")
        mode = "interval"

    if mode == "heartbeat":
        _run_heartbeat_daemon(config, force_reconnect, clean_start)
    else:
        _run_interval_daemon(config, force_reconnect, clean_start)


def _run_interval_daemon(config: Config, force_reconnect: bool, clean_start: bool) -> None:
    """Original fixed-interval reconnect loop."""
    interval = config.reconnect_interval_min
    do_force = force_reconnect or config.force_reconnect
    do_clean = clean_start or config.clean_start
    log.info(
        f"Daemon started (interval mode). Reconnect every {interval} min. "
        f"Force-reconnect: {do_force}. Clean-start: {do_clean}."
    )

    first_cycle = True
    while True:
        _fire_hooks(_before_reconnect_hooks, "before_reconnect")

        if do_force and not first_cycle:
            log.info("Force-reconnect: disconnecting before reconnect cycle.")
            launcher = VPNLauncher(config)
            launcher.disconnect()
            time.sleep(3)

        try:
            success = do_connect(config, disconnect_first=(do_clean and first_cycle))
            status = "connected" if success else "connect FAILED"
        except Exception as e:
            log.error(f"Connect error: {e}")
            status = "error"

        _fire_hooks(_after_reconnect_hooks, "after_reconnect")
        first_cycle = False

        next_time = datetime.now() + timedelta(minutes=interval)
        log.info(f"Status: {status}. Next reconnect at {next_time.strftime('%H:%M:%S')}.")

        try:
            time.sleep(interval * 60)
        except KeyboardInterrupt:
            log.info("Daemon stopped by user.")
            break


def _run_heartbeat_daemon(config: Config, force_reconnect: bool, clean_start: bool) -> None:
    """Heartbeat-based daemon: monitor connectivity, reconnect on failure."""
    do_force = force_reconnect or config.force_reconnect
    do_clean = clean_start or config.clean_start
    poll = config.heartbeat_interval_sec
    threshold = config.heartbeat_fail_threshold

    log.info(
        f"Daemon started (heartbeat mode). Poll: {poll}s, threshold: {threshold} failures. "
        f"Force-reconnect: {do_force}. Clean-start: {do_clean}."
    )

    # Initial connect
    _fire_hooks(_before_reconnect_hooks, "before_reconnect")
    try:
        do_connect(config, disconnect_first=do_clean)
    except Exception as e:
        log.error(f"Initial connect error: {e}")
    _fire_hooks(_after_reconnect_hooks, "after_reconnect")

    consecutive_failures = 0
    backoff_multiplier = 1
    last_forced = datetime.now()

    try:
        while True:
            time.sleep(poll * backoff_multiplier)

            # Forced periodic reconnect (safety net for expiring sessions)
            if do_force:
                elapsed = (datetime.now() - last_forced).total_seconds()
                if elapsed >= config.reconnect_interval_min * 60:
                    log.info(f"Forced reconnect ({config.reconnect_interval_min} min interval).")
                    _fire_hooks(_before_reconnect_hooks, "before_reconnect")
                    try:
                        do_connect(config, disconnect_first=True)
                    except Exception as e:
                        log.error(f"Forced reconnect error: {e}")
                    _fire_hooks(_after_reconnect_hooks, "after_reconnect")
                    last_forced = datetime.now()
                    consecutive_failures = 0
                    backoff_multiplier = 1
                    continue

            # Heartbeat check
            if is_host_reachable(config.test_domain, timeout=3):
                log.debug("Heartbeat OK.")
                if consecutive_failures > 0:
                    log.info(f"Connectivity restored after {consecutive_failures} failed heartbeat(s).")
                consecutive_failures = 0
                backoff_multiplier = 1
                continue

            consecutive_failures += 1
            log.warning(f"Heartbeat failed ({consecutive_failures}/{threshold}).")

            if consecutive_failures < threshold:
                continue

            # Threshold reached — reconnect
            log.info("Heartbeat threshold reached — triggering reconnect.")
            _fire_hooks(_before_reconnect_hooks, "before_reconnect")
            try:
                success = do_connect(config, disconnect_first=True)
            except Exception as e:
                log.error(f"Reconnect error: {e}")
                success = False
            _fire_hooks(_after_reconnect_hooks, "after_reconnect")

            if success:
                consecutive_failures = 0
                backoff_multiplier = 1
                last_forced = datetime.now()
            else:
                consecutive_failures = 0  # reset counter, let threshold accumulate again
                backoff_multiplier = min(backoff_multiplier * 2, 60)  # cap: poll*60 = 5*60 = 300s
                log.warning(
                    f"Reconnect failed. Backing off to {poll * backoff_multiplier}s between checks."
                )

    except KeyboardInterrupt:
        log.info("Daemon stopped by user.")
