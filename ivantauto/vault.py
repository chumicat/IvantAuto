"""Credential vault — stores secrets in Windows Credential Manager via keyring."""

import getpass

import keyring
import pyotp

SERVICE_NAME = "IvantAuto"


class CredentialNotFoundError(Exception):
    pass


def _key(username: str, kind: str) -> str:
    return f"{username}:{kind}"


def setup_credentials(username: str) -> None:
    """Interactive first-run setup: prompt for password and TOTP secret, store in keyring."""
    print(f"Setting up credentials for user: {username}")
    print()

    # Password
    password = getpass.getpass("VPN password: ")
    if not password:
        raise ValueError("Password cannot be empty.")
    keyring.set_password(SERVICE_NAME, _key(username, "password"), password)
    print("  Password saved to Windows Credential Manager.")

    # TOTP secret
    print()
    print("Enter your TOTP base32 secret (the seed key, NOT the 6-digit code).")
    print("You can export this from Google Authenticator or your TOTP app.")
    totp_secret = getpass.getpass("TOTP secret: ").strip().replace(" ", "")
    if not totp_secret:
        raise ValueError("TOTP secret cannot be empty.")

    # Validate it produces a code
    try:
        pyotp.TOTP(totp_secret).now()
    except Exception:
        raise ValueError("Invalid TOTP secret — could not generate a code. Check the base32 string.")

    keyring.set_password(SERVICE_NAME, _key(username, "totp_secret"), totp_secret)
    print("  TOTP secret saved to Windows Credential Manager.")
    print()
    print("Setup complete. Run 'ivantauto connect' to test.")


def get_password(username: str) -> str:
    """Retrieve VPN password from keyring."""
    pw = keyring.get_password(SERVICE_NAME, _key(username, "password"))
    if pw is None:
        raise CredentialNotFoundError(
            f"No password stored for '{username}'. Run 'ivantauto setup' first."
        )
    return pw


def get_totp_secret(username: str) -> str:
    """Retrieve TOTP secret from keyring."""
    secret = keyring.get_password(SERVICE_NAME, _key(username, "totp_secret"))
    if secret is None:
        raise CredentialNotFoundError(
            f"No TOTP secret stored for '{username}'. Run 'ivantauto setup' first."
        )
    return secret


def clear_credentials(username: str) -> None:
    """Remove all stored credentials for a user."""
    for kind in ("password", "totp_secret"):
        try:
            keyring.delete_password(SERVICE_NAME, _key(username, kind))
        except keyring.errors.PasswordDeleteError:
            pass
    print(f"Credentials cleared for '{username}'.")
