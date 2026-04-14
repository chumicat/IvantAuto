"""TOTP code generator — thin wrapper around pyotp."""

import time

import pyotp


class TOTPGenerator:
    def __init__(self, secret: str):
        self._totp = pyotp.TOTP(secret)
        # Validate immediately
        self._totp.now()

    def current_code(self) -> str:
        """Generate the current 6-digit TOTP code."""
        return self._totp.now()

    def seconds_remaining(self) -> int:
        """Seconds until the current code expires (30-second window)."""
        return 30 - (int(time.time()) % 30)
