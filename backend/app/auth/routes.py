from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.auth.store import AuthAlreadySetupError, AuthError

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE = "lorechat_session"
GUEST_COOKIE = "lorechat_guest"
_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 3600
_GUEST_COOKIE_MAX_AGE_SECONDS = 2 * 3600


def set_guest_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        GUEST_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=_GUEST_COOKIE_MAX_AGE_SECONDS,
    )


class SetupBody(BaseModel):
    password: str


class LoginBody(BaseModel):
    password: str


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


def _demo_enabled(request: Request) -> bool:
    return bool(request.app.state.settings_store.get().demo_mode)


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=_COOKIE_MAX_AGE_SECONDS,
    )


@router.post("/guest")
def auth_guest(request: Request, response: Response):
    if not _demo_enabled(request):
        return Response(
            status_code=403,
            content='{"detail": "demo mode disabled", "code": "demo_disabled"}',
            media_type="application/json",
        )
    guests = request.app.state.guest_sessions
    client = request.client
    sid = guests.create(ip=client.host if client else None)
    set_guest_cookie(response, sid)
    return {"ok": True, "role": "guest"}


@router.get("/status")
def auth_status(request: Request):
    auth = request.app.state.auth_store
    sessions = request.app.state.session_store
    sid = request.cookies.get(COOKIE)
    authenticated = sessions.validate(sid)
    demo = _demo_enabled(request)
    role = getattr(request.state, "identity", "none")
    return {
        "setup_required": False if demo else auth.is_setup_required(),
        "authenticated": authenticated,
        "demo": demo,
        "role": role,
    }


@router.post("/setup")
def auth_setup(body: SetupBody, request: Request, response: Response):
    if _demo_enabled(request):
        return Response(
            status_code=403,
            content='{"detail": "setup disabled in demo", "code": "demo_setup_disabled"}',
            media_type="application/json",
        )
    auth = request.app.state.auth_store
    sessions = request.app.state.session_store
    try:
        auth.set_password(body.password)
    except AuthAlreadySetupError:
        return Response(
            status_code=403,
            content='{"detail": "already set up", "code": "already_setup"}',
            media_type="application/json",
        )
    except AuthError as exc:
        return Response(
            status_code=400,
            content=f'{{"detail": "{exc}", "code": "invalid_password"}}',
            media_type="application/json",
        )
    sid = sessions.create()
    _set_session_cookie(response, sid)
    return {"ok": True}


@router.post("/login")
def auth_login(body: LoginBody, request: Request, response: Response):
    auth = request.app.state.auth_store
    sessions = request.app.state.session_store
    if auth.is_setup_required():
        return Response(
            status_code=400,
            content='{"detail": "setup required", "code": "setup_required"}',
            media_type="application/json",
        )
    if not auth.verify(body.password):
        return Response(
            status_code=401,
            content='{"detail": "invalid password", "code": "invalid_password"}',
            media_type="application/json",
        )
    sid = sessions.create()
    _set_session_cookie(response, sid)
    return {"ok": True}


@router.post("/logout")
def auth_logout(request: Request, response: Response):
    sessions = request.app.state.session_store
    sid = request.cookies.get(COOKIE)
    sessions.revoke(sid)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/change-password")
def auth_change_password(body: ChangePasswordBody, request: Request, response: Response):
    auth = request.app.state.auth_store
    sessions = request.app.state.session_store
    try:
        auth.change_password(body.old_password, body.new_password)
    except AuthError as exc:
        return Response(
            status_code=401,
            content=f'{{"detail": "{exc}", "code": "invalid_password"}}',
            media_type="application/json",
        )
    sid = request.cookies.get(COOKIE)
    sessions.revoke(sid)
    new_sid = sessions.create()
    _set_session_cookie(response, new_sid)
    return {"ok": True}
