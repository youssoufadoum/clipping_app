"""Build response models with batched queries (no N+1 lookups in list views)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AssetType, Clip, MediaAsset, ProcessingJob, Project
from app.schemas import ClipOut, JobOut, ProjectOut
from app.services.storage import get_storage
from app.worker.tasks import settings_hash

THUMB_TTL = 900


def _latest_jobs(
    db: Session, column: object, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, ProcessingJob]:
    if not ids:
        return {}
    rows = db.scalars(
        select(ProcessingJob)
        .where(column.in_(ids))  # type: ignore[attr-defined]
        .ext(distinct_on(column))  # type: ignore[arg-type]
        .order_by(column, ProcessingJob.created_at.desc())  # type: ignore[arg-type]
    )
    return {getattr(j, column.key): j for j in rows}  # type: ignore[attr-defined]


def _signed(key: str | None) -> str | None:
    if not key:
        return None
    ttl = min(THUMB_TTL, get_settings().s3_signed_url_ttl_seconds)
    return get_storage().signed_download_url(key, ttl)


def projects_out(db: Session, projects: Sequence[Project]) -> list[ProjectOut]:
    ids = [p.id for p in projects]
    if not ids:
        return []
    counts = dict(
        db.execute(
            select(Clip.project_id, func.count(Clip.id))
            .where(Clip.project_id.in_(ids))
            .group_by(Clip.project_id)
        ).all()
    )
    thumbs = dict(
        db.execute(
            select(MediaAsset.project_id, MediaAsset.storage_key).where(
                MediaAsset.project_id.in_(ids), MediaAsset.asset_type == AssetType.thumbnail
            )
        ).all()
    )
    jobs = _latest_jobs(db, ProcessingJob.project_id, ids)
    out = []
    for p in projects:
        item = ProjectOut.model_validate(p)
        item.clip_count = int(counts.get(p.id, 0))
        item.thumbnail_url = _signed(thumbs.get(p.id))
        job = jobs.get(p.id)
        item.latest_job = JobOut.model_validate(job) if job else None
        out.append(item)
    return out


def project_out(db: Session, project: Project) -> ProjectOut:
    return projects_out(db, [project])[0]


def clips_out(db: Session, clips: Sequence[Clip]) -> list[ClipOut]:
    ids = [c.id for c in clips]
    if not ids:
        return []
    thumbs: dict[uuid.UUID, str] = {}
    for clip_id, key in db.execute(
        select(MediaAsset.clip_id, MediaAsset.storage_key)
        .where(MediaAsset.clip_id.in_(ids), MediaAsset.asset_type == AssetType.clip_thumbnail)
        .order_by(MediaAsset.created_at.asc())
    ).all():
        if clip_id is not None:
            thumbs[clip_id] = key  # last (newest) wins
    jobs = _latest_jobs(db, ProcessingJob.clip_id, ids)
    out = []
    for c in clips:
        item = ClipOut.model_validate(c)
        item.render_is_current = bool(
            c.rendered_settings_hash and c.rendered_settings_hash == settings_hash(c)
        )
        item.thumbnail_url = _signed(thumbs.get(c.id))
        job = jobs.get(c.id)
        item.latest_job = JobOut.model_validate(job) if job else None
        out.append(item)
    return out


def clip_out(db: Session, clip: Clip) -> ClipOut:
    return clips_out(db, [clip])[0]
