"""Single server-rendered device-status page."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.dashboard.service import DashboardAuthService, SessionRejected

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/")
async def dashboard_page(request: Request) -> Response:
    token = request.cookies.get("__Host-skybeat_session")
    if token is None:
        return RedirectResponse("/auth/google/login", status_code=303)
    service: DashboardAuthService = request.app.state.dashboard_auth_service
    try:
        user = await asyncio.to_thread(service.authenticate_session, token)
    except SessionRejected:
        response = RedirectResponse("/auth/google/login", status_code=303)
        response.delete_cookie("__Host-skybeat_session", secure=True, httponly=True, path="/")
        return response
    dashboard_response = templates.TemplateResponse(
        request, "dashboard.html", {"user_email": user.email}
    )
    dashboard_response.headers["Cache-Control"] = "no-store"
    return dashboard_response
