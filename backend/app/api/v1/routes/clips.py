from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, rate_limit
from app.api.v1.serializers import clip_out, clips_out
from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, QuotaExceeded, ServiceUnavailable, ValidationFailed
from app.db.session import get_db
from app.models import (
    AssetType,
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
from app.schemas import ClipCreate, ClipOut, ClipUpdate, JobOut, MediaOut, Page, SignedUrlOut
from app.services import usage
from app.services.access import get_clip, get_media, get_project
from app.services.jobs import active_jobs, create_job, dispatch
from app.services.storage import get_storage

router = APIRouter(tags=["clips"])

MIN_CLIP_SECONDS = 1.0
MAX_CLIP_SECONDS = 10 * 60.0
CLIP_READY_STATUSES = {
    ProjectStatus.ready,
    ProjectStatus.completed,
    ProjectStatus.partially_failed,
    ProjectStatus.rendering,
}


def _validate_range(project: Project, start: float, end: float) -> tuple[float, float]:
    duration = project.source_duration_seconds or 0.0
    start, end = round(start, 3), round(end, 3)
    if end <= start:
        raise ValidationFailed("The end time must be after the start time.")
    if end > duration + 0.001:
        raise ValidationFailed(f"The clip must end within the video ({duration:.1f}s).")
    length = end - start
    if length < MIN_CLIP_SECONDS:
        raise ValidationFailed(f"Clips must be at least {MIN_CLIP_SECONDS:.0f} second long.")
    if length > MAX_CLIP_SECONDS:
        raise ValidationFailed(f"Clips can be at most {MAX_CLIP_SECONDS / 60:.0f} minutes long.")
    return start, min(end, duration)


def _require_ready(project: Project) -> None:
    if project.status not in CLIP_READY_STATUSES or not project.source_duration_seconds:
        raise Conflict("The video must finish processing before clips can be created.")


@router.get("/projects/{project_id}/clips", response_model=list[ClipOut])
def list_clips(
    project_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> list[ClipOut]:
    project = get_project(db, user, project_id)
    clips = list(
        db.scalars(
            select(Clip)
            .where(Clip.project_id == project.id)
            .order_by(Clip.start_seconds, Clip.created_at)
        )
    )
    return clips_out(db, clips)


@router.post(
    "/projects/{project_id}/clips",
    response_model=ClipOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("clip-create", 200, 3600))],
)
def create_clip(
    project_id: uuid.UUID,
    body: ClipCreate,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> ClipOut:
    project = get_project(db, user, project_id)
    _require_ready(project)
    start, end = _validate_range(project, body.start_seconds, body.end_seconds)
    clip = Clip(
        project_id=project.id,
        title=body.title.strip(),
        start_seconds=start,
        end_seconds=end,
        duration_seconds=round(end - start, 3),
        origin="manual",
        status=ClipStatus.draft,
        render_settings=body.render_settings.model_dump(),
    )
    db.add(clip)
    db.commit()
    return clip_out(db, clip)


@router.get("/clips/{clip_id}", response_model=ClipOut)
def get_clip_detail(
    clip_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ClipOut:
    return clip_out(db, get_clip(db, user, clip_id))


@router.patch("/clips/{clip_id}", response_model=ClipOut)
def update_clip(
    clip_id: uuid.UUID,
    body: ClipUpdate,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> ClipOut:
    clip = get_clip(db, user, clip_id, lock=True)
    project = get_project(db, user, clip.project_id)
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise ValidationFailed("Title must not be blank.")
        clip.title = title
    if body.start_seconds is not None or body.end_seconds is not None:
        start, end = _validate_range(
            project,
            body.start_seconds if body.start_seconds is not None else clip.start_seconds,
            body.end_seconds if body.end_seconds is not None else clip.end_seconds,
        )
        clip.start_seconds, clip.end_seconds = start, end
        clip.duration_seconds = round(end - start, 3)
    if body.render_settings is not None:
        clip.render_settings = body.render_settings.model_dump()
    db.commit()
    return clip_out(db, clip)


@router.delete("/clips/{clip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clip(
    clip_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    clip = get_clip(db, user, clip_id, lock=True)
    for job in active_jobs(db, clip.project_id, clip_id=clip.id):
        job.cancel_requested = True
    storage = get_storage()
    for asset in db.scalars(select(MediaAsset).where(MediaAsset.clip_id == clip.id)):
        storage.delete(asset.storage_key)
    db.delete(clip)
    db.commit()


@router.post(
    "/clips/{clip_id}/duplicate", response_model=ClipOut, status_code=status.HTTP_201_CREATED
)
def duplicate_clip(
    clip_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ClipOut:
    clip = get_clip(db, user, clip_id)
    copy = Clip(
        project_id=clip.project_id,
        title=f"{clip.title} (copy)"[:200],
        start_seconds=clip.start_seconds,
        end_seconds=clip.end_seconds,
        duration_seconds=clip.duration_seconds,
        selection_reason=clip.selection_reason,
        engagement_score=clip.engagement_score,
        origin=clip.origin,
        transcript_excerpt=clip.transcript_excerpt,
        status=ClipStatus.draft,
        render_settings=dict(clip.render_settings),
    )
    db.add(copy)
    db.commit()
    return clip_out(db, copy)


def _start_render(db: Session, user: Profile, clip_id: uuid.UUID) -> ProcessingJob:
    clip = get_clip(db, user, clip_id, lock=True)
    project = get_project(db, user, clip.project_id)
    _require_ready(project)
    if active_jobs(db, project.id, JobType.render_clip, clip_id=clip.id):
        raise Conflict("This clip is already rendering.")
    needed = usage.minutes(clip.duration_seconds)
    remaining = usage.summary(db, user).render_minutes_remaining
    if needed > remaining:
        raise QuotaExceeded(
            f"Rendering this clip needs {needed:.1f} render minutes; {remaining:.1f} remain "
            "this month."
        )
    job = create_job(
        db,
        project=project,
        job_type=JobType.render_clip,
        requested_by=user.id,
        clip_id=clip.id,
        params={"start": clip.start_seconds, "end": clip.end_seconds},
    )
    clip.status = ClipStatus.queued
    db.commit()
    dispatch(job)
    return job


@router.post(
    "/clips/{clip_id}/render",
    response_model=JobOut,
    dependencies=[Depends(rate_limit("clip-render", 120, 3600))],
)
def render_clip(
    clip_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ProcessingJob:
    return _start_render(db, user, clip_id)


@router.post(
    "/clips/{clip_id}/exports",
    response_model=JobOut,
    dependencies=[Depends(rate_limit("clip-render", 120, 3600))],
)
def create_export(
    clip_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ProcessingJob:
    """Render an MP4 export of the clip with its current settings (same as /render)."""
    return _start_render(db, user, clip_id)


def _filename(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()[:80]
    return f"{slug or 'clip'}.mp4"


def _latest_render(db: Session, clip_id: uuid.UUID) -> MediaAsset:
    asset = db.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.clip_id == clip_id,
            MediaAsset.asset_type == AssetType.rendered_clip,
        )
        .order_by(MediaAsset.created_at.desc())
        .limit(1)
    )
    if asset is None:
        raise NotFound("This clip has not been rendered yet.", code="NOT_RENDERED")
    return asset


@router.get("/clips/{clip_id}/download", response_model=SignedUrlOut)
def download_clip(
    clip_id: uuid.UUID,
    inline: bool = False,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> SignedUrlOut:
    """Short-lived signed URL to the clip's most recent rendered MP4."""
    clip = get_clip(db, user, clip_id)
    asset = _latest_render(db, clip.id)
    ttl = get_settings().s3_signed_url_ttl_seconds
    name = _filename(clip.title)
    url = get_storage().signed_download_url(asset.storage_key, ttl, filename=name, inline=inline)
    return SignedUrlOut(url=url, expires_in=ttl, filename=name)


@router.post(
    "/clips/{clip_id}/captions", responses={503: {"description": "Captions are not available yet"}}
)
def generate_captions(
    clip_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    get_clip(db, user, clip_id)
    raise ServiceUnavailable(
        "Captions require transcription, which is not available yet.", code="FEATURE_UNAVAILABLE"
    )


# --- Export history -----------------------------------------------------------


@router.get("/exports", response_model=Page[MediaOut])
def list_exports(
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[MediaOut]:
    ws_ids = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
    stmt = (
        select(MediaAsset)
        .join(Project, Project.id == MediaAsset.project_id)
        .where(Project.workspace_id.in_(ws_ids), MediaAsset.asset_type == AssetType.rendered_clip)
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(MediaAsset.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(
        items=[MediaOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/exports/{export_id}", response_model=SignedUrlOut)
def get_export(
    export_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> SignedUrlOut:
    asset = get_media(db, user, export_id)
    if asset.asset_type != AssetType.rendered_clip:
        raise NotFound("Export not found.")
    clip = db.get(Clip, asset.clip_id) if asset.clip_id else None
    name = _filename(clip.title if clip else "clip")
    ttl = get_settings().s3_signed_url_ttl_seconds
    return SignedUrlOut(
        url=get_storage().signed_download_url(asset.storage_key, ttl, filename=name, inline=False),
        expires_in=ttl,
        filename=name,
    )
