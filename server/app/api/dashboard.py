"""Authenticated dashboard API dependencies and read endpoints."""

import asyncio
from collections.abc import Callable
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.api.auth import same_origin
from app.dashboard.authorization import requires
from app.dashboard.management import (
    DashboardManagementService,
    enrollment_credential_value,
)
from app.dashboard.read import DashboardNotFound, DashboardReadService
from app.dashboard.service import (
    DashboardAuthService,
    DashboardUser,
    SessionRejected,
    resolve_dashboard_user,
)
from app.db import Database
from app.devices.service import Conflict, IdentityError, NotFound
from app.models import ApplicationUser
from app.notifications.management import NotificationManagementService, NotificationProjectNotFound
from app.schemas.dashboard_management import (
    DeviceEnrollRequest,
    DeviceMonitoringUpdateRequest,
    DeviceProjectUpdateRequest,
    ProjectCreateRequest,
    canonical_uuid,
)
from app.schemas.notifications import ProjectNotificationUpdateRequest, project_identifier
from app.schemas.users import UserCreateRequest, UserUpdateRequest
from app.users.service import (
    UserConflict,
    UserPermissionDenied,
    UserRole,
    UserService,
    authorize_user_change,
)

router = APIRouter(prefix="/api/v1")


async def dashboard_user(request: Request) -> DashboardUser:
    token = request.cookies.get("__Host-skybeat_session")
    service: DashboardAuthService = request.app.state.dashboard_auth_service
    try:
        return await asyncio.to_thread(
            resolve_dashboard_user, request.app.state.settings, service, token
        )
    except SessionRejected as error:
        raise HTTPException(
            status_code=401,
            detail="Dashboard authentication is required.",
            headers={"Cache-Control": "no-store"},
        ) from error


DashboardUserDependency = Annotated[DashboardUser, Depends(dashboard_user)]
ManagementUserDependency = Annotated[
    DashboardUser, Depends(requires(dashboard_user, UserRole.OWNER, UserRole.ADMIN))
]
UserAdminDependency = Annotated[
    DashboardUser, Depends(requires(dashboard_user, UserRole.OWNER, UserRole.ADMIN))
]


def _management_service(request: Request, user: DashboardUser) -> DashboardManagementService:
    factory = cast(
        Callable[[Database, str], DashboardManagementService],
        request.app.state.dashboard_management_service_factory,
    )
    return factory(request.app.state.database, user.email)


def _user_service(request: Request, user: DashboardUser) -> UserService:
    factory = cast(Callable[..., UserService], request.app.state.user_service_factory)
    return factory(request.app.state.database, actor=user.email, actor_role=user.role)


def _notification_service(request: Request, user: DashboardUser) -> NotificationManagementService:
    factory = cast(
        Callable[..., NotificationManagementService],
        request.app.state.notification_management_service_factory,
    )
    return factory(request.app.state.database, actor=user.email)


def _user_projection(user: ApplicationUser) -> dict[str, object]:
    return {
        "user_id": user.id,
        "name": user.display_name,
        "email": user.email,
        "role": user.role,
        "active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


def _require_same_origin(request: Request) -> None:
    if not same_origin(request):
        raise HTTPException(
            status_code=403,
            detail="Dashboard request origin is invalid.",
            headers={"Cache-Control": "no-store"},
        )


def _management_error(error: IdentityError) -> HTTPException:
    if isinstance(error, NotFound):
        return HTTPException(
            status_code=404,
            detail="Requested device or project was not found.",
            headers={"Cache-Control": "no-store"},
        )
    if isinstance(error, Conflict):
        return HTTPException(
            status_code=409,
            detail="Dashboard change conflicts with the current state.",
            headers={"Cache-Control": "no-store"},
        )
    return HTTPException(
        status_code=422,
        detail="Dashboard management input is invalid.",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/projects")
async def projects(request: Request, _: DashboardUserDependency) -> JSONResponse:
    service: DashboardReadService = request.app.state.dashboard_read_service
    payload = await asyncio.to_thread(service.list_projects)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.post("/projects")
async def create_project(
    request: Request, payload: ProjectCreateRequest, user: ManagementUserDependency
) -> JSONResponse:
    _require_same_origin(request)
    try:
        service = _management_service(request, user)
        project = await asyncio.to_thread(service.create_project, payload)
    except IdentityError as error:
        raise _management_error(error) from error
    return JSONResponse({"project": project}, headers={"Cache-Control": "no-store"})


@router.get("/dashboard/overview")
async def dashboard_overview(request: Request, _: DashboardUserDependency) -> JSONResponse:
    service: DashboardReadService = request.app.state.dashboard_read_service
    payload = await asyncio.to_thread(service.overview)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.get("/notifications")
async def notifications(request: Request, user: ManagementUserDependency) -> JSONResponse:
    return JSONResponse(
        await asyncio.to_thread(_notification_service(request, user).list_projects),
        headers={"Cache-Control": "no-store"},
    )


@router.put("/notifications/{project_uuid}")
async def update_notifications(
    request: Request,
    project_uuid: str,
    payload: ProjectNotificationUpdateRequest,
    user: ManagementUserDependency,
) -> JSONResponse:
    _require_same_origin(request)
    try:
        result = await asyncio.to_thread(
            _notification_service(request, user).update_project,
            project_identifier(project_uuid),
            payload,
        )
    except (NotificationProjectNotFound, ValueError) as error:
        raise HTTPException(
            status_code=404 if isinstance(error, NotificationProjectNotFound) else 422,
            detail="Notification project is invalid.",
            headers={"Cache-Control": "no-store"},
        ) from error
    return JSONResponse({"notification": result}, headers={"Cache-Control": "no-store"})


@router.get("/users")
async def users(request: Request, user: UserAdminDependency) -> JSONResponse:
    items = await asyncio.to_thread(_user_service(request, user).list_users)
    return JSONResponse(
        {"items": [_user_projection(item) for item in items]}, headers={"Cache-Control": "no-store"}
    )


@router.post("/users")
async def create_user(
    request: Request, payload: UserCreateRequest, user: UserAdminDependency
) -> JSONResponse:
    _require_same_origin(request)
    try:
        authorize_user_change(user.role, requested_role=payload.role)
        created = await asyncio.to_thread(
            _user_service(request, user).create_user,
            email=payload.email,
            display_name=payload.display_name,
            role=payload.role,
        )
    except UserPermissionDenied as error:
        raise HTTPException(
            status_code=403,
            detail="Dashboard permission is denied.",
            headers={"Cache-Control": "no-store"},
        ) from error
    except UserConflict as error:
        raise HTTPException(
            status_code=409,
            detail="User change conflicts with policy.",
            headers={"Cache-Control": "no-store"},
        ) from error
    return JSONResponse({"user": _user_projection(created)}, headers={"Cache-Control": "no-store"})


@router.patch("/users/{user_id}")
async def update_user(
    request: Request,
    user_id: int,
    payload: UserUpdateRequest,
    user: UserAdminDependency,
) -> JSONResponse:
    _require_same_origin(request)
    if user_id < 1:
        raise HTTPException(
            status_code=422,
            detail="User identifier is invalid.",
            headers={"Cache-Control": "no-store"},
        )
    try:
        updated = await asyncio.to_thread(
            _user_service(request, user).update_user,
            user_id,
            display_name=payload.display_name,
            role=payload.role,
            is_active=payload.is_active,
        )
    except UserPermissionDenied as error:
        raise HTTPException(
            status_code=403,
            detail="Dashboard permission is denied.",
            headers={"Cache-Control": "no-store"},
        ) from error
    except UserConflict as error:
        raise HTTPException(
            status_code=409,
            detail="User change conflicts with policy.",
            headers={"Cache-Control": "no-store"},
        ) from error
    return JSONResponse({"user": _user_projection(updated)}, headers={"Cache-Control": "no-store"})


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


@router.post("/devices")
async def enroll_device(
    request: Request, payload: DeviceEnrollRequest, user: ManagementUserDependency
) -> JSONResponse:
    _require_same_origin(request)
    try:
        result = await asyncio.to_thread(_management_service(request, user).enroll_device, payload)
    except IdentityError as error:
        raise _management_error(error) from error
    return JSONResponse(
        {
            "device": result.device,
            "credential": enrollment_credential_value(result).get_secret_value(),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.patch("/devices/{device_uuid}/project")
async def move_device(
    request: Request,
    device_uuid: str,
    payload: DeviceProjectUpdateRequest,
    user: ManagementUserDependency,
) -> JSONResponse:
    _require_same_origin(request)
    try:
        device = await asyncio.to_thread(
            _management_service(request, user).move_device, canonical_uuid(device_uuid), payload
        )
    except (IdentityError, ValueError) as error:
        if isinstance(error, ValueError) and not isinstance(error, IdentityError):
            raise HTTPException(
                status_code=422,
                detail="Dashboard management input is invalid.",
                headers={"Cache-Control": "no-store"},
            ) from error
        raise _management_error(error) from error
    return JSONResponse({"device": device}, headers={"Cache-Control": "no-store"})


@router.patch("/devices/{device_uuid}/monitoring")
async def set_device_monitoring(
    request: Request,
    device_uuid: str,
    payload: DeviceMonitoringUpdateRequest,
    user: ManagementUserDependency,
) -> JSONResponse:
    _require_same_origin(request)
    try:
        service = _management_service(request, user)
        device = await asyncio.to_thread(
            service.set_device_enabled, canonical_uuid(device_uuid), payload
        )
    except (IdentityError, ValueError) as error:
        if isinstance(error, ValueError) and not isinstance(error, IdentityError):
            raise HTTPException(
                status_code=422,
                detail="Dashboard management input is invalid.",
                headers={"Cache-Control": "no-store"},
            ) from error
        raise _management_error(error) from error
    return JSONResponse({"device": device}, headers={"Cache-Control": "no-store"})


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
