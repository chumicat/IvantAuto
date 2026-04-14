"""CLI entry point — setup, connect, daemon, status, clear-creds, debug-windows."""

import argparse
import logging
import sys

from . import __version__


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_setup(args):
    from . import config as cfg
    from .vault import setup_credentials

    conf = cfg.load(args.config)
    setup_credentials(conf.username)


def cmd_connect(args):
    from . import config as cfg
    from .daemon import do_connect

    conf = cfg.load(args.config)
    success = do_connect(conf, disconnect_first=args.clean_start or conf.clean_start)
    sys.exit(0 if success else 1)


def cmd_daemon(args):
    from . import config as cfg
    from .daemon import run_daemon

    conf = cfg.load(args.config)
    run_daemon(conf, force_reconnect=args.force_reconnect, clean_start=args.clean_start,
               mode_override=args.mode)


def cmd_disconnect(args):
    from . import config as cfg
    from .launcher import VPNLauncher

    conf = cfg.load(args.config)
    launcher = VPNLauncher(conf)
    success = launcher.disconnect()
    sys.exit(0 if success else 1)


def cmd_status(args):
    from . import config as cfg
    from .launcher import VPNLauncher

    conf = cfg.load(args.config)
    launcher = VPNLauncher(conf)

    if not conf.test_domain:
        print("No test_domain configured — cannot check status.")
        sys.exit(2)

    if launcher.is_already_connected():
        print(f"VPN is UP (ping to {conf.test_domain} succeeded).")
        sys.exit(0)
    else:
        print(f"VPN is DOWN (ping to {conf.test_domain} failed).")
        sys.exit(1)


def cmd_clear_creds(args):
    from . import config as cfg
    from .vault import clear_credentials

    conf = cfg.load(args.config)
    clear_credentials(conf.username)


def cmd_debug_windows(args):
    import sys
    from .utils import list_window_titles

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Listing all visible window titles (refresh every 2s, Ctrl+C to stop):")
    print()
    import time
    try:
        while True:
            titles = list_window_titles()
            print(f"--- {len(titles)} windows ---")
            for t in sorted(titles):
                print(f"  {t}".encode("utf-8", errors="replace").decode("utf-8"))
            print()
            time.sleep(2)
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(
        prog="ivantauto",
        description="IvantAuto — Ivanti Secure Access Client auto-connect with TOTP",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("-c", "--config", default="config.ini", help="Path to config.ini")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Store VPN credentials in Windows Credential Manager")
    connect_parser = sub.add_parser("connect", help="One-shot: connect to VPN with TOTP")
    connect_parser.add_argument(
        "--clean-start",
        action="store_true",
        default=False,
        help="Disconnect first before connecting (overrides config.ini)",
    )
    sub.add_parser("disconnect", help="Disconnect the VPN")
    daemon_parser = sub.add_parser("daemon", help="Persistent loop: auto-reconnect every N minutes")
    daemon_parser.add_argument(
        "--clean-start",
        action="store_true",
        default=False,
        help="Disconnect before the first connect cycle (overrides config.ini)",
    )
    daemon_parser.add_argument(
        "--force-reconnect",
        action="store_true",
        default=False,
        help="Disconnect before every reconnect cycle (overrides config.ini)",
    )
    daemon_parser.add_argument(
        "--mode",
        choices=["heartbeat", "interval"],
        default=None,
        help="Daemon mode: 'heartbeat' (monitor + reconnect on failure) or 'interval' (fixed timer). Default from config.ini.",
    )
    sub.add_parser("status", help="Check if VPN is currently connected")
    sub.add_parser("clear-creds", help="Remove stored credentials")
    sub.add_parser("debug-windows", help="List all visible window titles (for finding OTP dialog)")

    args = parser.parse_args()
    _setup_logging(args.verbose)

    commands = {
        "setup": cmd_setup,
        "connect": cmd_connect,
        "disconnect": cmd_disconnect,
        "daemon": cmd_daemon,
        "status": cmd_status,
        "clear-creds": cmd_clear_creds,
        "debug-windows": cmd_debug_windows,
    }

    if args.command in commands:
        try:
            commands[args.command](args)
        except Exception as e:
            logging.getLogger("ivantauto").error(str(e))
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
