"""Application factory; startup never creates or migrates database tables."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.engine import make_url
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.health import router as health_router
from app.api.heartbeats import PerDeviceRateLimiter
from app.api.heartbeats import router as heartbeats_router
from app.config import Settings
from app.db import Database
from app.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, database: Database | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    url = config.database_url.get_secret_value()
    configure_logging(config.log_level, [url, make_url(url).password or ""])
    db = database if database is not None else Database(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("API started", extra={"event_type": "startup"})
        try:
            yield
        finally:
            db.dispose()
            logger.info("API stopped", extra={"event_type": "shutdown"})

    app = FastAPI(
        title="SkyBeat",
        lifespan=lifespan,
        docs_url="/docs" if config.enable_api_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.enable_api_docs else None,
    )
    app.state.database = db
    app.state.settings = config
    app.state.heartbeat_limiter = PerDeviceRateLimiter()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        logger.error(
            "Request failed",
            extra={"request_id": request_id, "error_category": type(error).__name__},
        )
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "Request could not be completed.",
                    "request_id": request_id,
                }
            },
            status_code=500,
            headers={"Cache-Control": "no-store", "X-Request-ID": request_id},
        )

    app.include_router(health_router)
    app.include_router(heartbeats_router)
    return app
