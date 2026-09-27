"""Single server-rendered device-status page."""

import asyncio
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.dashboard.redirects import login_error_message, safe_return_path
from app.dashboard.service import (
    DashboardAuthService,
    DashboardUser,
    SessionRejected,
    resolve_dashboard_user,
)
from app.users.service import UserRole

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


DashboardView = Literal["overview", "devices", "projects", "notifications", "users"]


def _login_redirect(return_path: str) -> RedirectResponse:
    return RedirectResponse(f"/login?next={quote(return_path, safe='/?=&')}", status_code=303)


async def _dashboard_user(
    request: Request, *, return_path: str = "/"
) -> DashboardUser | Response | None:
    token = request.cookies.get("__Host-skybeat_session")
    settings = request.app.state.settings
    if token is None and not settings.dev_auth_bypass:
        return None
    service: DashboardAuthService = request.app.state.dashboard_auth_service
    try:
        return await asyncio.to_thread(resolve_dashboard_user, settings, service, token)
    except SessionRejected:
        response = _login_redirect(return_path)
        response.delete_cookie("__Host-skybeat_session", secure=True, httponly=True, path="/")
        return response


async def render_dashboard_view(request: Request, active_view: DashboardView) -> Response:
    user = await _dashboard_user(request, return_path=request.url.path)
    if user is None:
        return _login_redirect(request.url.path)
    if isinstance(user, Response):
        return user
    dashboard_response = templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user_email": user.email,
            "user_role": user.role.value,
            "can_manage": user.role in {UserRole.OWNER, UserRole.ADMIN},
            "active_view": active_view,
        },
    )
    dashboard_response.headers["Cache-Control"] = "no-store"
    return dashboard_response


@router.get("/")
async def dashboard_page(request: Request) -> Response:
    user = await _dashboard_user(request, return_path="/")
    if user is None:
        return _login_redirect("/")
    if isinstance(user, Response):
        return user
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/login")
async def login_page(
    request: Request, next: str | None = None, error: str | None = None
) -> Response:
    user = await _dashboard_user(request)
    invalid_session = isinstance(user, Response)
    if user is not None and not invalid_session:
        return RedirectResponse("/dashboard", status_code=303)
    destination = safe_return_path(next)
    login_url = "/auth/google/login"
    if destination is not None:
        login_url += f"?next={quote(destination, safe='/?=&')}"
    response = templates.TemplateResponse(
        request,
        "login.html",
        {"login_url": login_url, "auth_error": login_error_message(error)},
    )
    if invalid_session:
        response.delete_cookie("__Host-skybeat_session", secure=True, httponly=True, path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/dashboard")
async def dashboard_overview(request: Request) -> Response:
    return await render_dashboard_view(request, "overview")


@router.get("/dashboard/devices")
async def dashboard_devices(request: Request) -> Response:
    return await render_dashboard_view(request, "devices")


@router.get("/dashboard/projects")
async def dashboard_projects(request: Request) -> Response:
    return await render_dashboard_view(request, "projects")


@router.get("/dashboard/users")
async def dashboard_users(request: Request) -> Response:
    user = await _dashboard_user(request, return_path="/dashboard/users")
    if user is None:
        return _login_redirect("/dashboard/users")
    if isinstance(user, Response):
        return user
    if user.role not in {UserRole.OWNER, UserRole.ADMIN}:
        raise HTTPException(
            status_code=403,
            detail="Dashboard permission is denied.",
            headers={"Cache-Control": "no-store"},
        )
    return await render_dashboard_view(request, "users")


@router.get("/dashboard/notifications")
async def dashboard_notifications(request: Request) -> Response:
    user = await _dashboard_user(request, return_path="/dashboard/notifications")
    if user is None:
        return _login_redirect("/dashboard/notifications")
    if isinstance(user, Response):
        return user
    if user.role not in {UserRole.OWNER, UserRole.ADMIN}:
        raise HTTPException(
            status_code=403,
            detail="Dashboard permission is denied.",
            headers={"Cache-Control": "no-store"},
        )
    return await render_dashboard_view(request, "notifications")
