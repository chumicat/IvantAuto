"""Configuration manager — loads config.ini and resolves paths."""

import configparser
import os
from dataclasses import dataclass, field
from typing import Optional


class ConfigError(Exception):
    pass


# Default install locations for pulselauncher.exe
_PULSELAUNCHER_CANDIDATES = [
    r"C:\Program Files (x86)\Common Files\Pulse Secure\Integration\pulselauncher.exe",
    r"C:\Program Files\Common Files\Pulse Secure\Integration\pulselauncher.exe",
    r"C:\Program Files (x86)\Pulse Secure\Pulse\pulselauncher.exe",
    r"C:\Program Files\Pulse Secure\Pulse\pulselauncher.exe",
]

# Default install locations for jamCommand.exe (used for clean disconnect)
_JAMCOMMAND_CANDIDATES = [
    r"C:\Program Files (x86)\Common Files\Pulse Secure\JamUI\jamCommand.exe",
    r"C:\Program Files\Common Files\Pulse Secure\JamUI\jamCommand.exe",
]


@dataclass
class Config:
    vpn_url: str
    username: str
    realm: str
    pulselauncher_path: str
    jamcommand_path: Optional[str] = None
    test_domain: Optional[str] = None
    injection_strategy: str = "window"
    otp_dialog_timeout: int = 60
    reconnect_interval_min: int = 55
    otp_window_titles: list[str] = field(default_factory=list)
    force_reconnect: bool = False
    clean_start: bool = False
    connect_verify_timeout: int = 60
    connect_max_retries: int = 2
    daemon_mode: str = "heartbeat"
    heartbeat_interval_sec: int = 5
    heartbeat_fail_threshold: int = 3


def _find_exe(candidates: list[str]) -> Optional[str]:
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def load(config_path: str = "config.ini") -> Config:
    """Load and validate configuration from an INI file."""
    if not os.path.isfile(config_path):
        raise ConfigError(
            f"Config file not found: {config_path}\n"
            f"Copy config.ini.template to config.ini and fill in your values."
        )

    cp = configparser.ConfigParser()
    cp.read(config_path)

    # Required fields
    try:
        vpn_url = cp.get("host", "url")
        username = cp.get("auth", "username")
        realm = cp.get("auth", "realm")
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        raise ConfigError(f"Missing required config field: {e}")

    if vpn_url in ("https://vpn.yourcompany.com/portal", "vpn.yourcompany.com"):
        raise ConfigError("Please update config.ini with your actual VPN URL.")

    # Optional fields
    test_domain = cp.get("host", "test_domain", fallback=None)
    if test_domain == "internal.yourcompany.com":
        test_domain = None

    # Resolve pulselauncher path
    launcher_path = cp.get("start", "pulselauncher_path", fallback="").strip()
    if not launcher_path:
        launcher_path = _find_exe(_PULSELAUNCHER_CANDIDATES)
    if not launcher_path or not os.path.isfile(launcher_path):
        raise ConfigError(
            f"pulselauncher.exe not found. Searched:\n"
            + "\n".join(f"  - {p}" for p in _PULSELAUNCHER_CANDIDATES)
            + "\nSet pulselauncher_path in config.ini if installed elsewhere."
        )

    # Resolve jamCommand path (optional — used for clean disconnect)
    jamcommand_path = _find_exe(_JAMCOMMAND_CANDIDATES)

    # Options
    strategy = cp.get("options", "injection_strategy", fallback="window")
    if strategy not in ("window", "loop"):
        raise ConfigError(f"Invalid injection_strategy: {strategy} (use 'window' or 'loop')")

    otp_timeout = cp.getint("options", "otp_dialog_timeout", fallback=60)
    reconnect_min = cp.getint("options", "reconnect_interval_min", fallback=55)
    connect_verify_timeout = cp.getint("options", "connect_verify_timeout", fallback=60)
    connect_max_retries = cp.getint("options", "connect_max_retries", fallback=2)

    # Custom OTP window titles
    titles_raw = cp.get("options", "otp_window_titles", fallback="").strip()
    otp_titles = [t.strip() for t in titles_raw.split(",") if t.strip()] if titles_raw else []

    # Daemon options
    force_reconnect = cp.getboolean("daemon", "force_reconnect", fallback=False)
    clean_start = cp.getboolean("options", "clean_start", fallback=False)
    daemon_mode = cp.get("daemon", "daemon_mode", fallback="heartbeat")
    if daemon_mode not in ("heartbeat", "interval"):
        raise ConfigError(f"Invalid daemon_mode: {daemon_mode} (use 'heartbeat' or 'interval')")
    heartbeat_interval_sec = cp.getint("daemon", "heartbeat_interval_sec", fallback=5)
    heartbeat_fail_threshold = cp.getint("daemon", "heartbeat_fail_threshold", fallback=3)

    return Config(
        vpn_url=vpn_url,
        username=username,
        realm=realm,
        pulselauncher_path=launcher_path,
        jamcommand_path=jamcommand_path,
        test_domain=test_domain,
        injection_strategy=strategy,
        otp_dialog_timeout=otp_timeout,
        reconnect_interval_min=reconnect_min,
        otp_window_titles=otp_titles,
        force_reconnect=force_reconnect,
        clean_start=clean_start,
        connect_verify_timeout=connect_verify_timeout,
        connect_max_retries=connect_max_retries,
        daemon_mode=daemon_mode,
        heartbeat_interval_sec=heartbeat_interval_sec,
        heartbeat_fail_threshold=heartbeat_fail_threshold,
    )
