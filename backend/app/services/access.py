"""Resource-level authorization helpers.

Every lookup is scoped to the authenticated user. Resources the user cannot
access are reported as "not found" so identifiers cannot be enumerated.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import Clip, MediaAsset, ProcessingJob, Profile, Project, WorkspaceMember


def accessible_workspace_ids(db: Session, user: Profile) -> list[uuid.UUID]:
    return list(
        db.scalars(select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id))
    )


def get_project(
    db: Session, user: Profile, project_id: uuid.UUID, *, lock: bool = False
) -> Project:
    stmt = select(Project).where(
        Project.id == project_id,
        Project.workspace_id.in_(
            select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        ),
    )
    if lock:
        stmt = stmt.with_for_update()
    project = db.scalar(stmt)
    if project is None:
        raise NotFound("Project not found.")
    return project


def get_clip(db: Session, user: Profile, clip_id: uuid.UUID, *, lock: bool = False) -> Clip:
    clip = db.get(Clip, clip_id, with_for_update=lock)
    if clip is None:
        raise NotFound("Clip not found.")
    try:
        get_project(db, user, clip.project_id)
    except NotFound:
        raise NotFound("Clip not found.") from None
    return clip


def get_job(db: Session, user: Profile, job_id: uuid.UUID) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise NotFound("Job not found.")
    try:
        get_project(db, user, job.project_id)
    except NotFound:
        raise NotFound("Job not found.") from None
    return job


def get_media(db: Session, user: Profile, media_id: uuid.UUID) -> MediaAsset:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise NotFound("Media not found.")
    try:
        get_project(db, user, asset.project_id)
    except NotFound:
        raise NotFound("Media not found.") from None
    return asset
