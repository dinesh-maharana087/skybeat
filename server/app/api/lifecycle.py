"""Fixed agent lifecycle operations; browser management and device self access stay separate."""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import same_origin
from app.api.dashboard import DashboardUserDependency, ManagementUserDependency
from app.devices.credentials import InvalidCredential, parse_credential
from app.devices.service import AuthenticationFailed, NotFound
from app.lifecycle.service import AgentLifecycleService, LifecycleConflict
from app.releases.service import ReleaseUnavailable

router = APIRouter(prefix="/api/v1")


class LifecycleReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    operation_id: str = Field(max_length=36)
    state: Literal[
        "DOWNLOADING",
        "VERIFYING",
        "INSTALLING",
        "RESTARTING",
        "VERIFYING_HEALTH",
        "SUCCEEDED",
        "FAILED",
        "ROLLED_BACK",
        "ROLLBACK_FAILED",
    ]
    failure_category: (
        Literal[
            "verification_failed",
            "installation_failed",
            "service_start_failed",
            "health_check_failed",
            "rollback_failed",
        ]
        | None
    ) = None
    failure_detail: (
        Literal[
            "archive_digest_mismatch",
            "bundle_verification_failed",
            "previous_release_mismatch",
            "installer_failed",
            "interrupted_switch",
            "rollback_target_unhealthy",
            "previous_service_unhealthy",
        ]
        | None
    ) = None
    previous_wheel_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    rollback_available: bool = False


def _service(request: Request) -> AgentLifecycleService:
    return AgentLifecycleService(
        request.app.state.database, request.app.state.agent_release_service
    )


def _token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or authorization.count(" ") != 1:
        raise HTTPException(401, "Device authentication failed.")
    token = authorization[7:]
    try:
        parse_credential(token)
    except InvalidCredential:
        raise HTTPException(401, "Device authentication failed.") from None
    return token


def _origin(request: Request) -> None:
    if not same_origin(request):
        raise HTTPException(403, "Request origin is not authorized.")


async def _empty_intent(request: Request) -> None:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 32:
            raise HTTPException(413, "Lifecycle request is too large.")
        body.extend(chunk)
    if body and body.strip() != b"{}":
        raise HTTPException(422, "Lifecycle request does not accept parameters.")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, (AuthenticationFailed, InvalidCredential)):
        return HTTPException(401, "Device authentication failed.")
    if isinstance(exc, NotFound):
        return HTTPException(404, "Lifecycle device or operation not found.")
    if isinstance(exc, LifecycleConflict):
        return HTTPException(409, str(exc))
    if isinstance(exc, (ReleaseUnavailable, SQLAlchemyError)):
        return HTTPException(503, "Approved release or lifecycle storage is unavailable.")
    return HTTPException(422, "Lifecycle request is invalid.")


@router.get("/devices/{device_uuid}/agent-lifecycle")
async def lifecycle_overview(
    request: Request, device_uuid: str, _: DashboardUserDependency
) -> JSONResponse:
    try:
        result = await asyncio.to_thread(_service(request).overview, device_uuid)
    except (NotFound, ValueError, SQLAlchemyError) as exc:
        raise _error(exc) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/devices/{device_uuid}/agent-lifecycle/upgrade")
async def request_upgrade(
    request: Request, device_uuid: str, user: ManagementUserDependency
) -> JSONResponse:
    _origin(request)
    await _empty_intent(request)
    try:
        result = await asyncio.to_thread(_service(request).request_upgrade, device_uuid, user.email)
    except (NotFound, LifecycleConflict, ReleaseUnavailable, SQLAlchemyError, ValueError) as exc:
        raise _error(exc) from exc
    return JSONResponse(result, status_code=202, headers={"Cache-Control": "no-store"})


@router.post("/devices/{device_uuid}/agent-lifecycle/rollback")
async def request_rollback(
    request: Request, device_uuid: str, user: ManagementUserDependency
) -> JSONResponse:
    _origin(request)
    await _empty_intent(request)
    try:
        result = await asyncio.to_thread(
            _service(request).request_rollback, device_uuid, user.email
        )
    except (NotFound, LifecycleConflict, SQLAlchemyError, ValueError) as exc:
        raise _error(exc) from exc
    return JSONResponse(result, status_code=202, headers={"Cache-Control": "no-store"})


@router.get("/agent-lifecycle/operation")
async def device_operation(request: Request) -> JSONResponse:
    try:
        result = await asyncio.to_thread(_service(request).device_operation, _token(request))
    except (AuthenticationFailed, SQLAlchemyError) as exc:
        raise _error(exc) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/agent-lifecycle/operation/{operation_id}/download", response_model=None)
async def device_release(request: Request, operation_id: str) -> FileResponse:
    try:
        archive = await asyncio.to_thread(
            _service(request).device_archive, _token(request), operation_id
        )
    except (AuthenticationFailed, NotFound, ReleaseUnavailable, SQLAlchemyError) as exc:
        raise _error(exc) from exc
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=archive.name,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/agent-lifecycle/report")
async def device_report(request: Request) -> JSONResponse:
    token = _token(request)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 1024:
            raise HTTPException(413, "Lifecycle report is too large.")
        body.extend(chunk)
    try:
        report = LifecycleReport.model_validate(json.loads(body))
    except (ValueError, ValidationError):
        raise HTTPException(422, "Lifecycle report is invalid.") from None
    try:
        result = await asyncio.to_thread(
            _service(request).device_report,
            token,
            report.operation_id,
            report.state,
            failure_category=report.failure_category,
            failure_detail=report.failure_detail,
            previous_wheel_sha256=report.previous_wheel_sha256,
            rollback_available=report.rollback_available,
        )
    except (AuthenticationFailed, NotFound, LifecycleConflict, SQLAlchemyError, ValueError) as exc:
        raise _error(exc) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})
