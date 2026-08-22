"""Access control for the settings API.

The settings endpoints accept API keys, so who can reach them matters more than
it does for the rest of the app.

Two modes, chosen by whether `REELFORGE_ADMIN_TOKEN` is set:

  unset  loopback only. Anyone on the machine can configure it; nobody off it
         can. This is the right default for a single-user tool and needs no
         setup at all.
  set    any host, but a matching bearer token is required. Set it when the
         port is published beyond localhost.

The failure message says which mode is active, because "403" with no
explanation is how people end up disabling the check entirely.
"""
from __future__ import annotations

import hmac
import ipaddress
import os

from fastapi import HTTPException, Request

TOKEN_ENV = "REELFORGE_ADMIN_TOKEN"


def admin_token() -> str | None:
    return (os.environ.get(TOKEN_ENV) or "").strip() or None


def is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    if host in ("localhost", "testclient", ""):
        return True  # TestClient reports no meaningful peer
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_admin(request: Request) -> None:
    """Guard for anything that reads or writes configuration."""
    token = admin_token()

    if token is None:
        if is_loopback(request):
            return
        raise HTTPException(
            403,
            "Settings can only be changed from this machine. To administer "
            f"ReelForge remotely, set {TOKEN_ENV} and send it as a bearer token.",
        )

    header = request.headers.get("authorization", "")
    supplied = header[7:].strip() if header.lower().startswith("bearer ") else ""
    # constant-time: a token check that leaks timing is not a token check
    if supplied and hmac.compare_digest(supplied, token):
        return
    raise HTTPException(
        401,
        f"This ReelForge requires an admin token. Send the value of {TOKEN_ENV} "
        "as `Authorization: Bearer <token>`.",
    )


def access_mode() -> dict:
    """What the UI shows about how this instance is protected."""
    return {
        "mode": "token" if admin_token() else "loopback",
        "token_env": TOKEN_ENV,
        "description": (
            "An admin token is required for settings changes."
            if admin_token() else
            "Settings can be changed from this machine only. Set "
            f"{TOKEN_ENV} to allow remote administration."
        ),
    }
