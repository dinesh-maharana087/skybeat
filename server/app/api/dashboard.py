"""Authenticated dashboard API dependencies and read endpoints."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.dashboard.read import DashboardNotFound, DashboardReadService
from app.dashboard.service import DashboardAuthService, DashboardUser, SessionRejected

router = APIRouter(prefix="/api/v1")


async def dashboard_user(request: Request) -> DashboardUser:
    token = request.cookies.get("__Host-skybeat_session")
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Dashboard authentication is required.",
            headers={"Cache-Control": "no-store"},
        )
    service: DashboardAuthService = request.app.state.dashboard_auth_service
    try:
        return await asyncio.to_thread(service.authenticate_session, token)
    except SessionRejected as error:
        raise HTTPException(
            status_code=401,
            detail="Dashboard authentication is required.",
            headers={"Cache-Control": "no-store"},
        ) from error


DashboardUserDependency = Annotated[DashboardUser, Depends(dashboard_user)]


@router.get("/projects")
async def projects(request: Request, _: DashboardUserDependency) -> JSONResponse:
    service: DashboardReadService = request.app.state.dashboard_read_service
    payload = await asyncio.to_thread(service.list_projects)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.get("/dashboard/overview")
async def dashboard_overview(request: Request, _: DashboardUserDependency) -> JSONResponse:
    service: DashboardReadService = request.app.state.dashboard_read_service
    payload = await asyncio.to_thread(service.overview)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.get("/devices")
async def devices(
    request: Request,
    _: DashboardUserDependency,
    limit: int = Query(default=50, ge=1, le=100),
    project_id: str | None = None,
    state: str | None = None,
    include_disabled: bool = False,
    search: str | None = None,
    gpu_state: str | None = Query(default=None, max_length=32),
    cursor: str | None = Query(default=None, max_length=512),
) -> JSONResponse:
    service: DashboardReadService = request.app.state.dashboard_read_service
    try:
        payload = await asyncio.to_thread(
            service.list_devices,
            project_id=project_id,
            state=state,
            include_disabled=include_disabled,
            search=search,
            gpu_state=gpu_state,
            cursor=cursor,
            limit=limit,
        )
    except (DashboardNotFound, ValueError) as error:
        raise HTTPException(status_code=422, detail="Dashboard query is invalid.") from error
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.get("/incidents")
async def incidents(
    request: Request,
    _: DashboardUserDependency,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    device_id: str | None = Query(default=None, max_length=36),
) -> JSONResponse:
    service: DashboardReadService = request.app.state.dashboard_read_service
    try:
        payload = await asyncio.to_thread(
            service.list_incidents, limit=limit, cursor=cursor, device_id=device_id
        )
    except (DashboardNotFound, ValueError) as error:
        raise HTTPException(status_code=422, detail="Dashboard query is invalid.") from error
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.get("/devices/{device_uuid}/history")
async def device_history(
    request: Request,
    device_uuid: str,
    _: DashboardUserDependency,
    range_name: str = Query(alias="range", min_length=2, max_length=3),
) -> JSONResponse:
    service: DashboardReadService = request.app.state.dashboard_read_service
    try:
        payload = await asyncio.to_thread(service.device_history, device_uuid, range_name)
    except DashboardNotFound as error:
        raise HTTPException(status_code=404, detail="Device not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Dashboard query is invalid.") from error
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.get("/devices/{device_uuid}")
async def device(request: Request, device_uuid: str, _: DashboardUserDependency) -> JSONResponse:
    service: DashboardReadService = request.app.state.dashboard_read_service
    try:
        payload = await asyncio.to_thread(service.get_device, device_uuid)
    except DashboardNotFound as error:
        raise HTTPException(status_code=404, detail="Device not found.") from error
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.get("/devices/{device_uuid}/alerts")
async def device_alerts(
    request: Request,
    device_uuid: str,
    _: DashboardUserDependency,
    limit: int = Query(default=50, ge=1, le=100),
) -> JSONResponse:
    service: DashboardReadService = request.app.state.dashboard_read_service
    try:
        payload = await asyncio.to_thread(service.list_alerts, device_uuid, limit)
    except DashboardNotFound as error:
        raise HTTPException(status_code=404, detail="Device not found.") from error
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})
