from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, rate_limit
from app.api.v1.serializers import project_out, projects_out
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, QuotaExceeded, ServiceUnavailable, ValidationFailed
from app.core.plans import get_plan
from app.db.session import get_db
from app.models import (
    AssetType,
    AuditEvent,
    Clip,
    ClipStatus,
    JobType,
    MediaAsset,
    ProcessingJob,
    Profile,
    Project,
    ProjectStatus,
    WorkspaceMember,
)
from app.schemas import (
    ImportUrlRequest,
    JobOut,
    MediaOut,
    Page,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    UploadComplete,
    UploadCompleteOut,
    UploadInitiate,
    UploadTargetOut,
)
from app.services import usage
from app.services.access import get_media, get_project
from app.services.accounts import personal_workspace
from app.services.importers.youtube import canonical_url, parse_youtube_url
from app.services.jobs import active_jobs, create_job, dispatch, transition_project
from app.services.media.probe import ALLOWED_CONTAINERS, ALLOWED_EXTENSIONS, sniff_container
from app.services.storage import get_storage, project_prefix

router = APIRouter(tags=["projects"])
log = logging.getLogger(__name__)

UPLOAD_URL_TTL = 3600
PROCESSING_STATUSES = {
    ProjectStatus.importing,
    ProjectStatus.queued,
    ProjectStatus.inspecting,
    ProjectStatus.transcribing,
    ProjectStatus.analyzing,
    ProjectStatus.generating,
    ProjectStatus.rendering,
}


@router.post(
    "/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("project-create", 60, 3600))],
)
def create_project(
    body: ProjectCreate, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ProjectOut:
    plan = get_plan(user.plan_code)
    count = db.scalar(select(func.count(Project.id)).where(Project.owner_id == user.id)) or 0
    if count >= plan.max_projects:
        raise QuotaExceeded(
            f"Your plan allows {plan.max_projects} projects. Delete a project or upgrade."
        )
    ws = personal_workspace(db, user.id)
    project = Project(
        workspace_id=ws.id, owner_id=user.id, title=body.title, status=ProjectStatus.draft
    )
    db.add(project)
    db.commit()
    return project_out(db, project)


@router.post(
    "/projects/import",
    response_model=UploadCompleteOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("url-import", 20, 3600))],
)
def import_from_url(
    body: ImportUrlRequest, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> UploadCompleteOut:
    """Create a project from a YouTube link. The worker downloads it, then processing continues
    exactly as for an upload (inspection, then AI shorts if requested)."""
    settings = get_settings()
    if not settings.youtube_import_enabled:
        raise ServiceUnavailable(
            "YouTube import is turned off on this server.", code="URL_IMPORT_DISABLED"
        )
    if not body.rights_confirmed:
        raise ValidationFailed(
            "Confirm that you own this video or have permission to use it.",
            code="RIGHTS_NOT_CONFIRMED",
        )
    video_id = parse_youtube_url(body.url)
    if video_id is None:
        raise ValidationFailed(
            "Paste a link to a single YouTube video, like youtube.com/watch?v=… or youtu.be/….",
            code="UNSUPPORTED_URL",
        )
    plan = get_plan(user.plan_code)
    count = db.scalar(select(func.count(Project.id)).where(Project.owner_id == user.id)) or 0
    if count >= plan.max_projects:
        raise QuotaExceeded(
            f"Your plan allows {plan.max_projects} projects. Delete a project or upgrade."
        )
    if usage.summary(db, user).source_minutes_remaining <= 0:
        raise QuotaExceeded("You have used all of this month's source minutes.")

    ws = personal_workspace(db, user.id)
    title = (body.title or "").strip()
    processing: dict[str, object] = {
        "import": {
            "provider": "youtube",
            "video_id": video_id,
            "url": canonical_url(video_id),
            "placeholder_title": not title,
            "rights_confirmed_at": datetime.now(UTC).isoformat(),
        }
    }
    if body.auto_shorts is not None and settings.ai_configured:
        processing["auto_shorts"] = body.auto_shorts.model_dump()
    project = Project(
        workspace_id=ws.id,
        owner_id=user.id,
        title=title or "YouTube video",
        source_type="youtube",
        status=ProjectStatus.importing,
        processing_settings=processing,
    )
    db.add(project)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="import.rights_confirmed",
            target_type="project",
            target_id=str(project.id),
            metadata_={"url": canonical_url(video_id)},
        )
    )
    job = create_job(db, project=project, job_type=JobType.import_url, requested_by=user.id)
    db.commit()
    dispatch(job)
    return UploadCompleteOut(project=project_out(db, project), job=JobOut.model_validate(job))


@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=200),
    status_filter: str | None = Query(None, alias="status", max_length=32),
    include_archived: bool = False,
    sort: Literal["created_desc", "created_asc", "title"] = "created_desc",
) -> Page[ProjectOut]:
    ws_ids = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
    stmt = select(Project).where(Project.workspace_id.in_(ws_ids))
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Project.title.ilike(f"%{escaped}%", escape="\\"))
    if status_filter:
        stmt = stmt.where(Project.status == status_filter)
    elif not include_archived:
        stmt = stmt.where(Project.status != ProjectStatus.archived)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order: Any = {
        "created_desc": Project.created_at.desc(),
        "created_asc": Project.created_at.asc(),
        "title": Project.title.asc(),
    }[sort]
    rows = list(
        db.scalars(stmt.order_by(order, Project.id).offset((page - 1) * page_size).limit(page_size))
    )
    return Page(items=projects_out(db, rows), total=total, page=page, page_size=page_size)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project_detail(
    project_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ProjectOut:
    return project_out(db, get_project(db, user, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = get_project(db, user, project_id, lock=True)
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise ValidationFailed("Title must not be blank.")
        project.title = title
    if body.archived is True and project.status != ProjectStatus.archived:
        if project.status in PROCESSING_STATUSES:
            raise Conflict("Wait for processing to finish before archiving.")
        project.processing_settings = {
            **project.processing_settings,
            "status_before_archive": project.status,
        }
        transition_project(project, ProjectStatus.archived)
        project.archived_at = datetime.now(UTC)
    elif body.archived is False and project.status == ProjectStatus.archived:
        previous = project.processing_settings.get("status_before_archive", ProjectStatus.draft)
        restore = (
            previous
            if previous in (ProjectStatus.ready, ProjectStatus.failed)
            else (ProjectStatus.ready if project.source_duration_seconds else ProjectStatus.draft)
        )
        transition_project(project, restore)
        project.archived_at = None
    db.commit()
    return project_out(db, project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    project = get_project(db, user, project_id, lock=True)
    for job in active_jobs(db, project.id):
        job.cancel_requested = True
    db.commit()
    try:
        get_storage().delete_prefix(project_prefix(project.owner_id, project.id))
    except Exception:  # noqa: BLE001
        log.exception("storage deletion failed", extra={"project_id": project.id})
        raise AppError(
            "The project's media could not be deleted. Please try again.",
            code="DELETION_FAILED",
            status_code=503,
            retryable=True,
        ) from None
    db.delete(project)
    db.commit()


@router.get("/projects/{project_id}/jobs", response_model=list[JobOut])
def project_jobs(
    project_id: uuid.UUID,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
) -> list[ProcessingJob]:
    project = get_project(db, user, project_id)
    return list(
        db.scalars(
            select(ProcessingJob)
            .where(ProcessingJob.project_id == project.id)
            .order_by(ProcessingJob.created_at.desc())
            .limit(limit)
        )
    )


# --- Uploads ----------------------------------------------------------------


def _extension(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).suffix.lower()


@router.post(
    "/projects/{project_id}/uploads/initiate",
    response_model=UploadTargetOut,
    dependencies=[Depends(rate_limit("upload-initiate", 30, 3600))],
)
def initiate_upload(
    project_id: uuid.UUID,
    body: UploadInitiate,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> UploadTargetOut:
    settings = get_settings()
    project = get_project(db, user, project_id, lock=True)
    if project.status not in (ProjectStatus.draft, ProjectStatus.uploading):
        raise Conflict("This project already has a video. Create a new project to upload another.")

    ext = _extension(body.filename)
    content_type = body.content_type.lower().split(";")[0].strip()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationFailed(
            "Unsupported file type. Upload an MP4, MOV or WebM video.", code="UNSUPPORTED_MEDIA"
        )
    if content_type not in ALLOWED_CONTAINERS:
        # Browsers sometimes report an empty or generic type; infer from the extension.
        content_type = next(m for m, exts in ALLOWED_CONTAINERS.items() if ext in exts)

    plan = get_plan(user.plan_code)
    max_bytes = min(plan.max_upload_bytes, settings.max_upload_bytes)
    if body.size_bytes > max_bytes:
        raise QuotaExceeded(
            f"The file is larger than the {max_bytes / 1024**3:.1f} GB limit for your plan.",
            code="FILE_TOO_LARGE",
        )
    if usage.summary(db, user).source_minutes_remaining <= 0:
        raise QuotaExceeded("You have used all of this month's source minutes.")

    upload_id = uuid.uuid4()
    key = f"{project_prefix(project.owner_id, project.id)}source/{upload_id}{ext}"
    target = get_storage().create_upload(key, content_type, body.size_bytes, UPLOAD_URL_TTL)
    project.processing_settings = {
        **project.processing_settings,
        "pending_upload": {
            "id": str(upload_id),
            "key": key,
            "filename": body.filename[:255],
            "size": body.size_bytes,
            "content_type": content_type,
        },
    }
    transition_project(project, ProjectStatus.uploading)
    db.commit()
    return UploadTargetOut(
        upload_id=upload_id,
        method=target.method,
        url=target.url,
        headers=target.headers,
        expires_in=target.expires_in,
        max_bytes=max_bytes,
    )


@router.post("/projects/{project_id}/uploads/complete", response_model=UploadCompleteOut)
def complete_upload(
    project_id: uuid.UUID,
    body: UploadComplete,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> UploadCompleteOut:
    storage = get_storage()
    project = get_project(db, user, project_id, lock=True)
    pending = project.processing_settings.get("pending_upload")
    if (
        project.status != ProjectStatus.uploading
        or not pending
        or pending.get("id") != str(body.upload_id)
    ):
        existing = db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.idempotency_key == f"inspect:{body.upload_id}"
            )
        )
        if existing is not None:  # idempotent replay of a completed request
            return UploadCompleteOut(
                project=project_out(db, project), job=JobOut.model_validate(existing)
            )
        raise Conflict("No matching upload is in progress for this project.")

    key = pending["key"]
    info = storage.head(key)
    if info is None:
        raise ValidationFailed(
            "The upload did not reach storage. Please retry the upload.", code="UPLOAD_MISSING"
        )
    if info.size != pending["size"]:
        storage.delete(key)
        raise ValidationFailed(
            "The uploaded file is incomplete. Please retry the upload.", code="UPLOAD_INCOMPLETE"
        )
    sniffed = sniff_container(storage.read_prefix(key, 64))
    if sniffed is None:
        storage.delete(key)
        project.processing_settings = {
            k: v for k, v in project.processing_settings.items() if k != "pending_upload"
        }
        transition_project(project, ProjectStatus.draft)
        db.commit()
        raise ValidationFailed(
            "The file is not a valid MP4, MOV or WebM video.", code="UNSUPPORTED_MEDIA"
        )

    project.source_type = "upload"
    project.source_storage_key = key
    project.source_filename = pending["filename"]
    project.source_size_bytes = info.size
    project.source_mime_type = sniffed
    project.processing_settings = {
        k: v for k, v in project.processing_settings.items() if k != "pending_upload"
    }
    if body.auto_shorts is not None and get_settings().ai_configured:
        # Picked up by the worker once inspection succeeds.
        project.processing_settings = {
            **project.processing_settings,
            "auto_shorts": body.auto_shorts.model_dump(),
        }
    db.add(
        MediaAsset(
            project_id=project.id,
            asset_type=AssetType.source_video,
            storage_key=key,
            mime_type=sniffed,
            size_bytes=info.size,
        )
    )
    transition_project(project, ProjectStatus.queued)
    job = create_job(
        db,
        project=project,
        job_type=JobType.inspect_media,
        requested_by=user.id,
        idempotency_key=f"inspect:{body.upload_id}",
    )
    db.commit()
    dispatch(job)
    return UploadCompleteOut(project=project_out(db, project), job=JobOut.model_validate(job))


@router.post("/projects/{project_id}/uploads/abort", response_model=ProjectOut)
def abort_upload(
    project_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ProjectOut:
    """Abandon an in-progress upload (e.g. after the user cancels it in the browser)."""
    project = get_project(db, user, project_id, lock=True)
    pending = project.processing_settings.get("pending_upload")
    if project.status != ProjectStatus.uploading:
        raise Conflict("No upload is in progress.")
    if pending:
        try:
            get_storage().delete(pending["key"])
        except Exception:  # noqa: BLE001
            log.warning("could not delete partial upload", extra={"project_id": project.id})
    project.processing_settings = {
        k: v for k, v in project.processing_settings.items() if k != "pending_upload"
    }
    transition_project(project, ProjectStatus.draft)
    db.commit()
    return project_out(db, project)


# --- Media ------------------------------------------------------------------


@router.get("/projects/{project_id}/media", response_model=list[MediaOut])
def list_media(
    project_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> list[MediaAsset]:
    project = get_project(db, user, project_id)
    return list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.project_id == project.id)
            .order_by(MediaAsset.created_at.desc())
        )
    )


@router.get("/projects/{project_id}/source-url")
def source_url(
    project_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    """Short-lived URL for previewing the source video in the editor."""
    project = get_project(db, user, project_id)
    if not project.source_storage_key or project.status in (
        ProjectStatus.draft,
        ProjectStatus.uploading,
    ):
        raise Conflict("This project has no uploaded video yet.")
    ttl = get_settings().s3_signed_url_ttl_seconds
    return {
        "url": get_storage().signed_download_url(project.source_storage_key, ttl),
        "expires_in": ttl,
    }


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(
    media_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    asset = get_media(db, user, media_id)
    if asset.asset_type == AssetType.source_video:
        raise Conflict("Delete the project to remove its source video.")
    get_storage().delete(asset.storage_key)
    clip_id = asset.clip_id
    db.delete(asset)
    db.flush()
    if clip_id and asset.asset_type == AssetType.rendered_clip:
        remaining = db.scalar(
            select(func.count(MediaAsset.id)).where(
                MediaAsset.clip_id == clip_id, MediaAsset.asset_type == AssetType.rendered_clip
            )
        )
        clip = db.get(Clip, clip_id)
        if clip is not None and not remaining:
            clip.status = ClipStatus.draft
            clip.rendered_settings_hash = None
    db.commit()
