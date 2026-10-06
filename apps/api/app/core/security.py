"""Password hashing, opaque tokens and the short-lived realtime token."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class RealtimeClaims:
    user_id: str
    workspace_id: str
    expires_at: int


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_realtime_token(user_id: str, workspace_id: str, ttl_s: int = 120) -> str:
    body = _b64(json.dumps({"u": user_id, "w": workspace_id, "e": int(time.time()) + ttl_s}).encode())
    key = get_settings().realtime_token_secret.get_secret_value().encode()
    sig = _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_realtime_token(token: str) -> RealtimeClaims | None:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    key = get_settings().realtime_token_secret.get_secret_value().encode()
    expected = _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(data.get("e", 0)) < time.time():
        return None
    return RealtimeClaims(user_id=str(data["u"]), workspace_id=str(data["w"]), expires_at=int(data["e"]))


def sign_payload(secret: str, body: bytes, timestamp: int) -> str:
    """HMAC-SHA256 over `timestamp.body`, used for outbound webhooks and inbound triggers."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verify_signature(secret: str, body: bytes, header: str, tolerance_s: int = 300) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance_s:
        return False
    return hmac.compare_digest(sign_payload(secret, body, ts), header)
