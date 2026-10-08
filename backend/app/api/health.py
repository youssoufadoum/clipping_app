from __future__ import annotations

import shutil

import redis
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.errors import Forbidden
from app.db.session import get_engine, get_sessionmaker
from app.models import ProcessingJob
from app.services.storage import get_storage

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> JSONResponse:
    """Dependency readiness. Reports pass/fail only; never connection details."""
    checks: dict[str, bool] = {}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:  # noqa: BLE001
        checks["database"] = False
    try:
        checks["queue"] = bool(
            redis.Redis.from_url(get_settings().redis_url, socket_timeout=2).ping()
        )
    except Exception:  # noqa: BLE001
        checks["queue"] = False
    try:
        checks["storage"] = get_storage().check()
    except Exception:  # noqa: BLE001
        checks["storage"] = False
    checks["ffmpeg"] = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    ok = all(checks.values())
    return JSONResponse(
        {"status": "ready" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503
    )


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def metrics(authorization: str = Header(default="")) -> str:
    token = get_settings().metrics_token
    if not token or authorization != f"Bearer {token}":
        raise Forbidden()
    with get_sessionmaker()() as db:
        rows = db.execute(
            select(ProcessingJob.job_type, ProcessingJob.status, func.count()).group_by(
                ProcessingJob.job_type, ProcessingJob.status
            )
        ).all()
    lines = ["# TYPE virello_jobs gauge"]
    lines += [f'virello_jobs{{type="{t}",status="{s}"}} {c}' for t, s, c in rows]
    return "\n".join(lines) + "\n"
