"""Protected access to the configured immutable agent release."""

import asyncio
from typing import cast

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import same_origin
from app.api.dashboard import ManagementUserDependency
from app.local_release_status import store_status
from app.releases.registry import ManagedReleaseService, ReleaseConflict
from app.releases.service import ReleaseMetadata, ReleaseUnavailable

router = APIRouter(prefix="/api/v1/agent-releases")


def _service(request: Request) -> ManagedReleaseService:
    return cast(ManagedReleaseService, request.app.state.agent_release_service)


class RegisterRelease(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(
        min_length=1, max_length=80, pattern=r"^skybeat-agent-[0-9]+\.[0-9]+\.[0-9]+$"
    )


def _origin(request: Request) -> None:
    if not same_origin(request):
        raise HTTPException(403, "Request origin is not authorized.")


@router.get("")
async def list_releases(request: Request, _: ManagementUserDependency) -> JSONResponse:
    try:
        rows = await asyncio.to_thread(_service(request).list)
    except SQLAlchemyError:
        return _unavailable(request)
    storage = store_status(_service(request).store.root)
    return JSONResponse(
        {"releases": rows, "storage_status": storage}, headers={"Cache-Control": "no-store"}
    )


@router.post("", status_code=201)
async def register_release(
    request: Request, payload: RegisterRelease, user: ManagementUserDependency
) -> JSONResponse:
    _origin(request)
    try:
        release = await asyncio.to_thread(_service(request).register, payload.name, user.email)
    except ReleaseConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ReleaseUnavailable, SQLAlchemyError):
        return _unavailable(request)
    return JSONResponse(
        {"release": release}, status_code=201, headers={"Cache-Control": "no-store"}
    )


@router.post("/{digest}/verify")
async def verify_release(
    request: Request,
    user: ManagementUserDependency,
    digest: str = Path(pattern=r"^[0-9a-f]{64}$"),
) -> JSONResponse:
    _origin(request)
    try:
        release = await asyncio.to_thread(_service(request).verify, digest, user.email)
    except (ReleaseUnavailable, SQLAlchemyError):
        return _unavailable(request)
    return JSONResponse({"release": release}, headers={"Cache-Control": "no-store"})


@router.post("/{digest}/activate")
async def activate_release(
    request: Request,
    user: ManagementUserDependency,
    digest: str = Path(pattern=r"^[0-9a-f]{64}$"),
) -> JSONResponse:
    _origin(request)
    try:
        release = await asyncio.to_thread(_service(request).activate, digest, user.email)
    except (ReleaseUnavailable, SQLAlchemyError):
        return _unavailable(request)
    return JSONResponse({"release": release}, headers={"Cache-Control": "no-store"})


def _projection(metadata: ReleaseMetadata, archive_sha256: str) -> dict[str, object]:
    return {
        "version": metadata.version,
        "archive_sha256": archive_sha256,
        "wheel_filename": metadata.wheel_filename,
        "wheel_sha256": metadata.wheel_sha256,
        "archive_filename": metadata.archive_filename,
        "archive_root": metadata.archive_root,
        "server_url": metadata.server_url,
        "allow_insecure_local_server": metadata.allow_insecure_local_server,
    }


def _unavailable(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": "agent_release_unavailable",
                "message": "Approved agent release is unavailable.",
                "request_id": request.state.request_id,
            }
        },
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/current")
async def current_release(request: Request, _: ManagementUserDependency) -> JSONResponse:
    try:
        artifact = await asyncio.to_thread(_service(request).active_artifact)
    except (ReleaseUnavailable, SQLAlchemyError):
        return _unavailable(request)
    return JSONResponse(
        {"release": _projection(artifact.metadata, artifact.archive_sha256)},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/current/download", response_model=None)
async def download_current_release(
    request: Request,
    _: ManagementUserDependency,
    archive_sha256: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$"),
) -> FileResponse | JSONResponse:
    try:
        if archive_sha256 is None:
            archive = await asyncio.to_thread(_service(request).archive)
        else:
            archive = await asyncio.to_thread(_service(request).archive_by_digest, archive_sha256)
    except (ReleaseUnavailable, SQLAlchemyError):
        return _unavailable(request)
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=archive.name,
        headers={"Cache-Control": "no-store"},
    )
