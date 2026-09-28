"""Protected access to the configured immutable agent release."""

import asyncio
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app.api.dashboard import ManagementUserDependency
from app.releases.service import AgentReleaseService, ReleaseMetadata, ReleaseUnavailable

router = APIRouter(prefix="/api/v1/agent-releases")


def _service(request: Request) -> AgentReleaseService:
    return cast(AgentReleaseService, request.app.state.agent_release_service)


def _projection(metadata: ReleaseMetadata) -> dict[str, object]:
    return {
        "version": metadata.version,
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
        metadata = await asyncio.to_thread(_service(request).current)
    except ReleaseUnavailable:
        return _unavailable(request)
    return JSONResponse({"release": _projection(metadata)}, headers={"Cache-Control": "no-store"})


@router.get("/current/download", response_model=None)
async def download_current_release(
    request: Request, _: ManagementUserDependency
) -> FileResponse | JSONResponse:
    try:
        archive = await asyncio.to_thread(_service(request).archive)
    except ReleaseUnavailable:
        return _unavailable(request)
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=archive.name,
        headers={"Cache-Control": "no-store"},
    )
