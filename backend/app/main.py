from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import health
from app.api.v1.routes import (
    auth,
    clips,
    jobs,
    me,
    projects,
    storage_local,
    system,
    transcripts,
    usage,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, correlation_id_var

log = logging.getLogger("virello.api")


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "correlation_id": correlation_id_var.get(),
                "details": details or {},
            }
        },
        headers={"X-Correlation-ID": correlation_id_var.get() or ""},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            send_default_pii=False,
            traces_sample_rate=0.05,
        )

    app = FastAPI(
        title="Virello Studio API",
        version="0.1.0",
        description="Turn long videos into short, editable clips.",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID", "Content-Disposition"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get("x-correlation-id", "")
        cid = incoming if 8 <= len(incoming) <= 64 and incoming.isascii() else uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers["X-Correlation-ID"] = cid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.url.path not in ("/health",):
            log.info(
                "%s %s",
                request.method,
                request.url.path,
                extra={
                    "status": response.status_code,
                    "path": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return _error(
            exc.status_code, exc.code, exc.message, {**exc.details, "retryable": exc.retryable}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return _error(
            422, "VALIDATION_FAILED", "The request contains invalid data.", {"fields": fields}
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return _error(500, "INTERNAL_ERROR", "Something went wrong on our side.")

    app.include_router(health.router)
    api = "/api/v1"
    for module in (auth, me, system, projects, jobs, clips, transcripts, usage):
        app.include_router(module.router, prefix=api)
    if settings.storage_backend == "local":
        app.include_router(storage_local.router, prefix=api)
    return app


app = create_app()
