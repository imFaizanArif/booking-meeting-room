from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import Field

from app.api.deps import DB, Auth, client_ip, rate_limit
from app.core.config import get_settings
from app.core.enums import Role
from app.ratelimit.limiter import Limit
from app.schemas.common import Ok, Schema
from app.services import auth as service

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(Schema):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class MeOut(Schema):
    user_id: str
    email: str
    role: Role
    workspace_id: str
    csrf_token: str | None = None


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    settings = get_settings()
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=MeOut)
async def login(data: LoginIn, request: Request, response: Response, session: DB) -> MeOut:
    settings = get_settings()
    await rate_limit(f"login:{client_ip(request)}", Limit(settings.login_rate_per_minute, 60))
    await rate_limit(f"login:{data.email.lower()}", Limit(settings.login_rate_per_minute, 60))
    issued = await service.login(
        session, data.email, data.password, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    _set_cookies(response, issued.token, issued.csrf_token)
    ctx = issued.context
    return MeOut(
        user_id=str(ctx.user_id),
        email=ctx.email,
        role=ctx.role,
        workspace_id=str(ctx.workspace_id),
        csrf_token=issued.csrf_token,
    )


@router.post("/logout", response_model=Ok)
async def logout(request: Request, response: Response, ctx: Auth, session: DB) -> Ok:
    await service.logout(session, ctx, request.state.session_row_id)
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    return Ok()


@router.get("/me", response_model=MeOut)
async def me(ctx: Auth) -> MeOut:
    return MeOut(user_id=str(ctx.user_id), email=ctx.email, role=ctx.role, workspace_id=str(ctx.workspace_id))
