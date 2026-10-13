"""Narrow device log upload and dashboard recent-log read."""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.dashboard import DashboardUserDependency
from app.api.heartbeats import RequestBodyTooLarge, error
from app.dashboard.read import DashboardNotFound
from app.devices.credentials import InvalidCredential, parse_credential
from app.devices.service import AuthenticationFailed
from app.logs.correlation import IncidentDiagnosticService
from app.logs.service import LogRateLimited, LogTimestampInvalid, LogWatchService
from app.schemas.logs import MAX_LOG_BODY_BYTES, LogUploadInvalid, parse_log_upload

router = APIRouter()
logger = logging.getLogger(__name__)


async def _body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_LOG_BODY_BYTES:
            raise RequestBodyTooLarge()
        body.extend(chunk)
    return bytes(body)


@router.post("/api/v1/agent/logs")
async def upload_logs(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json" or request.headers.get("content-encoding"):
        return error(
            request, 415, "unsupported_media_type", "Log upload requires application/json."
        )
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > MAX_LOG_BODY_BYTES:
                return error(request, 413, "payload_too_large", "Log upload is too large.")
        except ValueError:
            return error(request, 400, "invalid_request", "Log upload request is invalid.")
    authorization = request.headers.get("authorization")
    if (
        not authorization
        or not authorization.startswith("Bearer ")
        or authorization.count(" ") != 1
    ):
        return error(request, 401, "authentication_failed", "Device authentication failed.")
    token = authorization[7:]
    try:
        parse_credential(token)
    except InvalidCredential:
        return error(request, 401, "authentication_failed", "Device authentication failed.")
    try:
        payload = parse_log_upload(await _body(request))
    except RequestBodyTooLarge:
        return error(request, 413, "payload_too_large", "Log upload is too large.")
    except LogUploadInvalid:
        return error(request, 422, "invalid_payload", "Log upload is invalid.")
    service = LogWatchService(
        request.app.state.database, allowed=request.app.state.log_limiter.allow
    )
    try:
        result = await asyncio.to_thread(service.accept, payload, token)
    except AuthenticationFailed:
        return error(request, 401, "authentication_failed", "Device authentication failed.")
    except LogRateLimited:
        logger.warning(
            "log_upload_rate_limited source=%s",
            payload.source,
            extra={"request_id": request.state.request_id},
        )
        return error(
            request,
            429,
            "rate_limited",
            "Log uploads are temporarily limited.",
            headers={"Retry-After": "60"},
        )
    except LogTimestampInvalid:
        return error(request, 422, "invalid_payload", "Log upload is invalid.")
    except SQLAlchemyError:
        return error(
            request, 503, "database_unavailable", "Log storage is temporarily unavailable."
        )
    logger.info(
        "log_upload_accepted source=%s accepted=%s duplicates=%s",
        payload.source,
        result["accepted"],
        result["duplicates"],
        extra={"request_id": request.state.request_id},
    )
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/api/v1/devices/{device_uuid}/logs")
async def recent_logs(
    request: Request,
    device_uuid: str,
    _: DashboardUserDependency,
    source: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=60, ge=1, le=100),
    from_time: str | None = Query(default=None, alias="from", max_length=40),
    until: str | None = Query(default=None, max_length=40),
    cursor: str | None = Query(default=None, max_length=2048),
    direction: Literal["newest", "oldest"] = "newest",
    q: str | None = Query(default=None, max_length=128),
    time_basis: Literal["received", "occurred"] = "received",
) -> JSONResponse:
    service = LogWatchService(request.app.state.database)
    try:
        result = await asyncio.to_thread(
            service.recent,
            device_uuid,
            source=source,
            limit=limit,
            from_time=from_time,
            until=until,
            cursor=cursor,
            direction=direction,
            q=q,
            time_basis=time_basis,
        )
    except DashboardNotFound as exc:
        raise HTTPException(
            status_code=404, detail="Device not found.", headers={"Cache-Control": "no-store"}
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Log query is invalid.", headers={"Cache-Control": "no-store"}
        ) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/api/v1/devices/{device_uuid}/incidents/{incident_uuid}/diagnostics")
async def incident_diagnostics(
    request: Request,
    device_uuid: str,
    incident_uuid: str,
    _: DashboardUserDependency,
    point: Literal["opened", "recovered"] = "opened",
) -> JSONResponse:
    service = IncidentDiagnosticService(request.app.state.database)
    try:
        result = await asyncio.to_thread(service.get, device_uuid, incident_uuid, point=point)
    except DashboardNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="Incident or device not found.",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Incident correlation point is invalid.",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except SQLAlchemyError:
        return error(
            request,
            503,
            "database_unavailable",
            "Incident diagnostics are temporarily unavailable.",
        )
    return JSONResponse(result, headers={"Cache-Control": "no-store"})
