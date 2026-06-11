"""Supabase token verification middleware for Flask routes.

Tokens are verified in two ways:
1. If SUPABASE_JWT_SECRET is set, verify the HS256 signature locally (fast).
2. Otherwise, call the Supabase Auth API (`/auth/v1/user`) — works with any
   project signing-key configuration (legacy HS256 or new asymmetric keys).
"""

from functools import wraps

import httpx
import jwt
from flask import g, request

from .config import Config
from .errors import ForbiddenError, UnauthorizedError

_user_cache: dict[str, str] = {}  # token -> user id (per-process, best effort)


def _extract_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing bearer token")
    return auth_header.removeprefix("Bearer ").strip()


def _verify_locally(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            Config.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid token") from exc
    return payload["sub"]


def _verify_via_auth_api(token: str) -> str:
    if token in _user_cache:
        return _user_cache[token]

    try:
        response = httpx.get(
            f"{Config.SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": Config.SUPABASE_ANON_KEY,
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise UnauthorizedError("Could not verify token with Supabase") from exc

    if response.status_code != 200:
        raise UnauthorizedError("Invalid or expired token")

    user_id = response.json().get("id")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    if len(_user_cache) > 1000:
        _user_cache.clear()
    _user_cache[token] = user_id
    return user_id


def _resolve_user_id(token: str) -> str:
    if Config.SUPABASE_JWT_SECRET:
        return _verify_locally(token)
    return _verify_via_auth_api(token)


def require_auth(fn):
    """Require a valid Supabase access token. Loads the caller's profile into g."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = _resolve_user_id(_extract_token())
        from .repositories.user_repository import UserRepository

        user = UserRepository().get_by_id(user_id)
        if user is None:
            raise UnauthorizedError("Profile not found for this token")
        if not user.is_active:
            raise ForbiddenError("Your account has been disabled. Contact an administrator.")

        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    """Require an authenticated admin user."""

    @wraps(fn)
    @require_auth
    def wrapper(*args, **kwargs):
        if g.current_user.role != "admin":
            raise ForbiddenError("Admin privileges required")
        return fn(*args, **kwargs)

    return wrapper
