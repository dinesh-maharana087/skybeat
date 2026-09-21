from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/livez")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readiness(request: Request) -> JSONResponse:
    ready = request.app.state.database.ready()
    return JSONResponse(
        {"status": "ok" if ready else "unavailable"},
        status_code=200 if ready else 503,
        headers={"Cache-Control": "no-store"},
    )
