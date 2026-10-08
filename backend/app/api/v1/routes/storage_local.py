"""Signed upload/download endpoints for the local storage backend.

Only mounted when ``STORAGE_BACKEND=local``. With S3 the browser talks to the
bucket directly via presigned URLs and these routes do not exist.
"""

from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from app.core.errors import AppError, Forbidden, NotFound, ValidationFailed
from app.services.storage import get_storage
from app.services.storage.local import LocalStorage

router = APIRouter(prefix="/storage/local", tags=["storage"], include_in_schema=False)
log = logging.getLogger(__name__)


def _local() -> LocalStorage:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise NotFound()
    return storage


@router.put("/upload")
async def upload(request: Request, token: str = Query(...)) -> Response:
    storage = _local()
    try:
        claims = storage.verify(token, "put")
    except PermissionError:
        raise Forbidden("This upload link is invalid or has expired.") from None
    if request.headers.get("content-type", "").split(";")[0] != claims["ct"]:
        raise ValidationFailed("Content-Type does not match the signed upload.")
    max_bytes = int(claims["max"])  # type: ignore[call-overload]
    declared = request.headers.get("content-length")
    if declared and int(declared) > max_bytes:
        raise ValidationFailed("The upload is larger than declared.", code="FILE_TOO_LARGE")

    dest = storage.path_for(str(claims["key"]))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{uuid.uuid4().hex}.part")
    written = 0
    try:
        fh = await run_in_threadpool(open, tmp, "wb")
        try:
            async for chunk in request.stream():
                written += len(chunk)
                if written > max_bytes:
                    raise ValidationFailed(
                        "The upload is larger than declared.", code="FILE_TOO_LARGE"
                    )
                await run_in_threadpool(fh.write, chunk)
        finally:
            await run_in_threadpool(fh.close)
        os.replace(tmp, dest)
    except AppError:
        tmp.unlink(missing_ok=True)
        raise
    except Exception:
        tmp.unlink(missing_ok=True)
        log.exception("local upload failed")
        raise AppError(
            "The upload failed. Please retry.",
            code="UPLOAD_FAILED",
            status_code=500,
            retryable=True,
        ) from None
    return Response(status_code=200, headers={"ETag": f'"{written}"'})


@router.get("/object")
def download(token: str = Query(...)) -> FileResponse:
    storage = _local()
    try:
        claims = storage.verify(token, "get")
    except PermissionError:
        raise Forbidden("This link is invalid or has expired.") from None
    path = storage.path_for(str(claims["key"]))
    if not path.is_file():
        raise NotFound()
    filename = str(claims.get("fn") or "") or None
    disposition = "inline" if claims.get("inline", True) else "attachment"
    media_type = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".m4v": "video/mp4",
        ".jpg": "image/jpeg",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type=disposition,
        headers={"Cache-Control": "private, max-age=300"},
    )
