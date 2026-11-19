"""Per-attempt bearer tokens that bind every gateway call to one run and one task.

The harness mints a token for each agent container from a batch secret only the
harness and the gateway hold, so the gateway can attribute usage (and refuse
unattributed spend) without a registration call, and an agent cannot forge a
token for another task.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Optional

PREFIX = "wcbt1"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint(key: bytes, run: str, task: str) -> str:
    payload = _b64(json.dumps({"run": run, "task": task}, sort_keys=True,
                              separators=(",", ":")).encode("utf-8"))
    mac = _b64(hmac.new(key, f"{PREFIX}.{payload}".encode("ascii"), hashlib.sha256).digest())
    return f"{PREFIX}.{payload}.{mac}"


def verify(key: bytes, token: str) -> Optional[dict]:
    """``{"run", "task"}`` for a token minted under ``key``, else None."""
    parts = (token or "").split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        return None
    expected = _b64(hmac.new(key, f"{PREFIX}.{parts[1]}".encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        return None
    try:
        claims = json.loads(_unb64(parts[1]))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(claims, dict) or not claims.get("run") or not claims.get("task"):
        return None
    return {"run": str(claims["run"]), "task": str(claims["task"])}
