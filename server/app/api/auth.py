"""Google login endpoints with opaque application-owned browser sessions."""

import asyncio
from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.dashboard.service import DashboardAuthError, DashboardAuthService, SessionRejected

router = APIRouter(prefix="/auth")

SESSION_COOKIE = "__Host-skybeat_session"
OAUTH_COOKIE = "__Host-skybeat_oauth"


class LoginRateLimiter:
    """Small per-process bound for the public login initiation endpoint."""

    def __init__(self) -> None:
        self._events: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, client_id: str) -> bool:
        now = monotonic()
        with self._lock:
            events = self._events[client_id]
            while events and events[0] <= now - 60:
                events.popleft()
            if len(events) >= 6:
                return False
            events.append(now)
            return True


def _callback_url(request: Request) -> str:
    return f"{request.app.state.settings.public_base_url.rstrip('/')}/auth/google/callback"


def _secure_cookie(response: Response, key: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key=key,
        value=value,
        max_age=max_age,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )


def same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    expected = request.app.state.settings.public_base_url.rstrip("/")
    candidate = origin or (
        f"{urlsplit(referer).scheme}://{urlsplit(referer).netloc}" if referer else None
    )
    return candidate is None or candidate == expected


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    client_id = request.client.host if request.client is not None else "unknown"
    if not request.app.state.login_rate_limiter.allow(client_id):
        raise HTTPException(
            status_code=429,
            detail="Google login is temporarily limited.",
            headers={"Cache-Control": "no-store", "Retry-After": "60"},
        )
    service: DashboardAuthService = request.app.state.dashboard_auth_service
    try:
        login = await service.begin_login(_callback_url(request))
    except DashboardAuthError as error:
        raise HTTPException(
            status_code=503,
            detail="Google authentication is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        ) from error
    response = RedirectResponse(login.url, status_code=307, headers={"Cache-Control": "no-store"})
    _secure_cookie(response, OAUTH_COOKIE, login.browser_binding, 600)
    return response


@router.get("/google/callback", name="google_callback")
async def google_callback(
    request: Request,
    state: str = Query(min_length=1, max_length=256),
    code: str = Query(min_length=1, max_length=4096),
) -> RedirectResponse:
    service: DashboardAuthService = request.app.state.dashboard_auth_service
    binding = request.cookies.get(OAUTH_COOKIE, "")
    try:
        token = await service.complete_login(
            state=state,
            code=code,
            browser_binding=binding,
            redirect_uri=_callback_url(request),
        )
    except SessionRejected as error:
        raise HTTPException(
            status_code=403,
            detail="Dashboard access is not authorized.",
            headers={"Cache-Control": "no-store"},
        ) from error
    except DashboardAuthError as error:
        raise HTTPException(
            status_code=401,
            detail="Google login could not be verified.",
            headers={"Cache-Control": "no-store"},
        ) from error
    response = RedirectResponse("/", status_code=303, headers={"Cache-Control": "no-store"})
    _secure_cookie(response, SESSION_COOKIE, token, 8 * 60 * 60)
    response.delete_cookie(OAUTH_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    if not same_origin(request):
        raise HTTPException(
            status_code=403,
            detail="Logout origin is invalid.",
            headers={"Cache-Control": "no-store"},
        )
    token = request.cookies.get(SESSION_COOKIE)
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Dashboard authentication is required.",
            headers={"Cache-Control": "no-store"},
        )
    service: DashboardAuthService = request.app.state.dashboard_auth_service
    try:
        await asyncio.to_thread(service.logout, token)
    except SessionRejected as error:
        raise HTTPException(
            status_code=401,
            detail="Dashboard authentication is required.",
            headers={"Cache-Control": "no-store"},
        ) from error
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
    return response
