"""Device-only heartbeat endpoint with strict transport and secret-safe errors."""

import asyncio
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.devices.credentials import InvalidCredential, parse_credential
from app.devices.service import AuthenticationFailed
from app.heartbeats.service import (
    HeartbeatConflict,
    HeartbeatIdentityMismatch,
    HeartbeatRateLimited,
    HeartbeatService,
)
from app.schemas.heartbeat import MAX_BODY_BYTES, HeartbeatValidationError, parse_heartbeat

router = APIRouter()


class RequestBodyTooLarge(ValueError):
    """Raised before more than the approved heartbeat body limit is retained."""


async def read_heartbeat_body(request: Request) -> bytes:
    """Read an ASGI request body while enforcing the cap for chunked transfers."""
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise RequestBodyTooLarge
        body.extend(chunk)
    return bytes(body)


class PerDeviceRateLimiter:
    """Small, bounded per-process limiter for the initial single-VM deployment."""

    def __init__(self) -> None:
        self._events: defaultdict[int, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, device_id: int) -> bool:
        now = monotonic()
        with self._lock:
            events = self._events[device_id]
            while events and events[0] <= now - 60:
                events.popleft()
            if len(events) >= 6:
                return False
            events.append(now)
            return True


def error(
    request: Request,
    status: int,
    code: str,
    message: str,
    *,
    fields: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error_body: dict[str, object] = {
        "code": code,
        "message": message,
        "request_id": request.state.request_id,
    }
    if fields:
        error_body["fields"] = fields
    return JSONResponse(
        {"error": error_body},
        status_code=status,
        headers={"Cache-Control": "no-store", **(headers or {})},
    )


@router.post("/api/v1/heartbeats")
async def receive_heartbeat(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json" or request.headers.get("content-encoding"):
        return error(request, 415, "unsupported_media_type", "Heartbeat requires application/json.")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > MAX_BODY_BYTES:
                return error(request, 413, "payload_too_large", "Heartbeat payload is too large.")
        except ValueError:
            return error(request, 400, "invalid_request", "Heartbeat request is invalid.")
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
        raw = await read_heartbeat_body(request)
    except RequestBodyTooLarge:
        return error(request, 413, "payload_too_large", "Heartbeat payload is too large.")
    try:
        heartbeat = parse_heartbeat(raw)
    except HeartbeatValidationError as exc:
        return error(
            request, exc.status_code, exc.code, "Heartbeat payload is invalid.", fields=exc.fields
        )
    service = HeartbeatService(
        request.app.state.database, allowed=request.app.state.heartbeat_limiter.allow
    )
    try:
        accepted = await asyncio.to_thread(service.accept, heartbeat, token)
    except AuthenticationFailed:
        return error(request, 401, "authentication_failed", "Device authentication failed.")
    except HeartbeatIdentityMismatch:
        return error(request, 403, "identity_mismatch", "Heartbeat identity is not authorized.")
    except HeartbeatRateLimited:
        return error(
            request,
            429,
            "rate_limited",
            "Heartbeat rate is temporarily limited.",
            headers={"Retry-After": "10"},
        )
    except HeartbeatConflict:
        return error(
            request,
            409,
            "heartbeat_id_conflict",
            "Heartbeat identifier conflicts with an existing snapshot.",
        )
    except SQLAlchemyError:
        return error(
            request, 503, "database_unavailable", "Heartbeat storage is temporarily unavailable."
        )
    return JSONResponse(accepted.payload, headers={"Cache-Control": "no-store"})
