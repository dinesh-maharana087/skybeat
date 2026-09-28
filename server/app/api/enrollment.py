"""One-time agent enrollment issuance, exchange, and narrow receipt verification."""

import asyncio
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import same_origin
from app.api.dashboard import ManagementUserDependency
from app.devices.service import Conflict, IdentityError, NotFound
from app.enrollment.service import (
    AgentEnrollmentService,
    EnrollmentMode,
    EnrollmentRejected,
    EnrollmentStatus,
    EnrollmentToken,
    ReceiptRejected,
    TokenRejected,
)
from app.schemas.enrollment import AgentEnrollmentIntentRequest

router = APIRouter(prefix="/api/v1/agent-enrollments")


class EnrollmentRateLimiter:
    """Bound anonymous exchange/receipt requests per source address."""

    def __init__(self) -> None:
        self._events: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, source: str) -> bool:
        now = monotonic()
        with self._lock:
            events = self._events[source]
            while events and events[0] <= now - 60:
                events.popleft()
            if len(events) >= 12:
                return False
            events.append(now)
            return True


def _service(request: Request, actor: str) -> AgentEnrollmentService:
    factory = cast(
        Callable[..., AgentEnrollmentService], request.app.state.agent_enrollment_service_factory
    )
    return factory(request.app.state.database, actor=actor)


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "request_id": request.state.request_id}},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def _bearer_token(request: Request, expected_prefix: str) -> str | None:
    authorization = request.headers.get("authorization")
    if (
        authorization is None
        or len(authorization) > 256
        or not authorization.startswith("Bearer ")
        or authorization.count(" ") != 1
    ):
        return None
    token = authorization[7:]
    try:
        EnrollmentToken.parse(token, expected_prefix=expected_prefix)
    except TokenRejected:
        return None
    return token


def _allow_anonymous_request(request: Request) -> bool:
    source = request.client.host if request.client is not None else "unknown"
    limiter = cast(EnrollmentRateLimiter, request.app.state.enrollment_rate_limiter)
    return limiter.allow(source)


def _status_projection(status: EnrollmentStatus) -> dict[str, object]:
    return {
        "enrollment_id": status.enrollment_id,
        "state": status.state.value,
        "expires_at": status.expires_at.isoformat(),
        "device_id": status.device_id,
        "last_seen_at": status.last_seen_at.isoformat() if status.last_seen_at else None,
    }


@router.post("")
async def create_intent(
    request: Request, payload: AgentEnrollmentIntentRequest, user: ManagementUserDependency
) -> JSONResponse:
    if not same_origin(request):
        raise HTTPException(
            status_code=403,
            detail="Dashboard request origin is invalid.",
            headers={"Cache-Control": "no-store"},
        )
    try:
        policy = None
        if payload.mode == EnrollmentMode.NEW.value:
            from app.devices.service import GPUPolicy

            policy = GPUPolicy(
                monitoring_enabled=cast(bool, payload.gpu_monitoring_enabled),
                min_count=cast(int, payload.expected_gpu_min_count),
            )
        issued = await asyncio.to_thread(
            _service(request, user.email).create_intent,
            mode=EnrollmentMode(payload.mode),
            project_uuid=payload.project_id,
            replacement_device_uuid=payload.device_id,
            device_name=payload.name,
            policy=policy,
        )
    except NotFound as error:
        raise HTTPException(
            status_code=404,
            detail="Requested device or project was not found.",
            headers={"Cache-Control": "no-store"},
        ) from error
    except Conflict as error:
        raise HTTPException(
            status_code=409,
            detail="Enrollment intent conflicts with the current state.",
            headers={"Cache-Control": "no-store"},
        ) from error
    except (IdentityError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail="Enrollment intent is invalid.",
            headers={"Cache-Control": "no-store"},
        ) from error
    return JSONResponse(
        {
            "enrollment": {
                "enrollment_id": issued.enrollment.public_id,
                "expires_at": issued.enrollment.expires_at.isoformat(),
            },
            "token": issued.token.value,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/exchange")
async def exchange(request: Request) -> JSONResponse:
    token = _bearer_token(request, "sbe1")
    if token is None:
        return _error(
            request, 401, "enrollment_authorization_invalid", "Enrollment authorization is invalid."
        )
    if not _allow_anonymous_request(request):
        return _error(request, 429, "rate_limited", "Enrollment exchange is temporarily limited.")
    expected_replacement_device_uuid: str | None = None
    expected_target = request.headers.get("X-SkyBeat-Reenroll-Device")
    if expected_target is not None:
        try:
            expected_replacement_device_uuid = str(UUID(expected_target))
        except ValueError:
            return _error(
                request,
                401,
                "enrollment_authorization_invalid",
                "Enrollment authorization is invalid.",
            )
    try:
        result = await asyncio.to_thread(
            _service(request, "agent-enrollment").exchange,
            token,
            expected_replacement_device_uuid=expected_replacement_device_uuid,
        )
    except EnrollmentRejected:
        return _error(
            request, 401, "enrollment_authorization_invalid", "Enrollment authorization is invalid."
        )
    except SQLAlchemyError:
        return _error(
            request, 503, "database_unavailable", "Enrollment is temporarily unavailable."
        )
    return JSONResponse(
        {
            "device_id": result.device.device_uuid,
            "credential": result.credential.token.get_secret_value(),
            "verification_token": result.verification_token.value,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/verification")
async def verify_receipt(request: Request) -> JSONResponse:
    token = _bearer_token(request, "sbv1")
    if token is None:
        return _error(
            request,
            401,
            "enrollment_receipt_invalid",
            "Enrollment verification receipt is invalid.",
        )
    if not _allow_anonymous_request(request):
        return _error(
            request, 429, "rate_limited", "Enrollment verification is temporarily limited."
        )
    try:
        result = await asyncio.to_thread(
            _service(request, "agent-enrollment").verify_receipt, token
        )
    except ReceiptRejected:
        return _error(
            request,
            401,
            "enrollment_receipt_invalid",
            "Enrollment verification receipt is invalid.",
        )
    except SQLAlchemyError:
        return _error(
            request, 503, "database_unavailable", "Enrollment verification is unavailable."
        )
    return JSONResponse(
        {"accepted_heartbeat": result.accepted_heartbeat}, headers={"Cache-Control": "no-store"}
    )


@router.get("/{enrollment_id}")
async def enrollment_status(
    request: Request, enrollment_id: str, user: ManagementUserDependency
) -> JSONResponse:
    try:
        enrollment_uuid = str(UUID(enrollment_id))
        status = await asyncio.to_thread(_service(request, user.email).status, enrollment_uuid)
    except (ValueError, NotFound) as error:
        raise HTTPException(
            status_code=422 if isinstance(error, ValueError) else 404,
            detail="Enrollment was not found."
            if isinstance(error, NotFound)
            else "Enrollment is invalid.",
            headers={"Cache-Control": "no-store"},
        ) from error
    return JSONResponse(
        {"enrollment": _status_projection(status)}, headers={"Cache-Control": "no-store"}
    )


@router.delete("/{enrollment_id}")
async def revoke_unused_enrollment(
    request: Request, enrollment_id: str, user: ManagementUserDependency
) -> JSONResponse:
    if not same_origin(request):
        raise HTTPException(
            status_code=403,
            detail="Dashboard request origin is invalid.",
            headers={"Cache-Control": "no-store"},
        )
    try:
        enrollment_uuid = str(UUID(enrollment_id))
        status = await asyncio.to_thread(
            _service(request, user.email).revoke_unused, enrollment_uuid
        )
    except (ValueError, NotFound, Conflict) as error:
        status_code = (
            422 if isinstance(error, ValueError) else 404 if isinstance(error, NotFound) else 409
        )
        raise HTTPException(
            status_code=status_code,
            detail="Enrollment change conflicts with the current state."
            if isinstance(error, Conflict)
            else "Enrollment was not found."
            if isinstance(error, NotFound)
            else "Enrollment is invalid.",
            headers={"Cache-Control": "no-store"},
        ) from error
    return JSONResponse(
        {"enrollment": _status_projection(status)}, headers={"Cache-Control": "no-store"}
    )
