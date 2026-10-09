from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, rate_limit
from app.core.config import get_settings
from app.core.errors import Conflict, QuotaExceeded, ServiceUnavailable, ValidationFailed
from app.db.session import get_db
from app.models import (
    Clip,
    ClipStatus,
    JobStatus,
    JobType,
    ProcessingJob,
    Profile,
    ProjectStatus,
    Transcript,
)
from app.schemas import AnalyzeRequest, JobOut
from app.services import usage
from app.services.access import get_job, get_project
from app.services.jobs import active_jobs, create_job, dispatch, transition_job, transition_project

router = APIRouter(tags=["jobs"])


class JobCreate(BaseModel):
    job_type: str


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job_status(
    job_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ProcessingJob:
    return get_job(db, user, job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ProcessingJob:
    locked = db.get(ProcessingJob, get_job(db, user, job_id).id, with_for_update=True)
    assert locked is not None
    job = locked
    if job.status not in (JobStatus.queued, JobStatus.running):
        raise Conflict("Only queued or running jobs can be cancelled.")
    job.cancel_requested = True
    if job.status == JobStatus.queued:
        # Not yet picked up: cancel immediately. A running job is stopped by the worker.
        transition_job(job, JobStatus.cancelled)
        job.stage = "cancelled"
        if job.job_type == JobType.inspect_media:
            project = get_project(db, user, job.project_id, lock=True)
            if project.status in (ProjectStatus.queued, ProjectStatus.inspecting):
                transition_project(project, ProjectStatus.cancelled)
        elif job.clip_id:
            clip = db.get(Clip, job.clip_id)
            if clip is not None:
                clip.status = (
                    ClipStatus.rendered if clip.rendered_settings_hash else ClipStatus.draft
                )
    db.commit()
    return job


def _retry(db: Session, user: Profile, job: ProcessingJob) -> ProcessingJob:
    project = get_project(db, user, job.project_id, lock=True)
    if job.job_type == JobType.inspect_media:
        if active_jobs(db, project.id, JobType.inspect_media):
            raise Conflict("This video is already being processed.")
        if project.status in (ProjectStatus.failed, ProjectStatus.cancelled):
            transition_project(project, ProjectStatus.queued)
        elif project.status != ProjectStatus.ready:
            raise Conflict("This project cannot be re-inspected right now.")
        else:
            raise Conflict("This video was already processed successfully.")
    elif job.job_type == JobType.generate_shorts:
        if active_jobs(db, project.id, JobType.generate_shorts):
            raise Conflict("AI is already working on this video.")
        if project.status != ProjectStatus.ready:
            raise Conflict("The video must be ready before AI can run again.")
    elif job.job_type == JobType.render_clip:
        if not job.clip_id or db.get(Clip, job.clip_id) is None:
            raise Conflict("The clip for this job no longer exists.")
        if active_jobs(db, project.id, JobType.render_clip, clip_id=job.clip_id):
            raise Conflict("This clip is already rendering.")
        clip = db.get(Clip, job.clip_id)
        assert clip is not None
        clip.status = ClipStatus.queued
    else:
        raise ServiceUnavailable("This job type cannot be retried.")
    new_job = create_job(
        db,
        project=project,
        job_type=job.job_type,
        requested_by=user.id,
        clip_id=job.clip_id,
        params={**job.params, "retry_of": str(job.id)},
    )
    db.commit()
    dispatch(new_job)
    return new_job


@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobOut,
    dependencies=[Depends(rate_limit("job-retry", 30, 3600))],
)
def retry_job(
    job_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> ProcessingJob:
    job = get_job(db, user, job_id)
    if job.status not in (JobStatus.failed, JobStatus.cancelled):
        raise Conflict("Only failed or cancelled jobs can be retried.")
    return _retry(db, user, job)


@router.post(
    "/projects/{project_id}/jobs",
    response_model=JobOut,
    dependencies=[Depends(rate_limit("job-create", 30, 3600))],
)
def create_project_job(
    project_id: uuid.UUID,
    body: JobCreate,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProcessingJob:
    """Start a project-level job. Clip renders use ``POST /clips/{id}/render``."""
    project = get_project(db, user, project_id, lock=True)
    if body.job_type != JobType.inspect_media:
        raise ValidationFailed("Supported job types: inspect_media.")
    if project.status not in (ProjectStatus.failed, ProjectStatus.cancelled):
        raise Conflict("Inspection can only be re-run after a failure or cancellation.")
    if not project.source_storage_key:
        raise Conflict("Upload a video first.")
    if active_jobs(db, project.id, JobType.inspect_media):
        raise Conflict("This video is already being processed.")
    transition_project(project, ProjectStatus.queued)
    job = create_job(db, project=project, job_type=JobType.inspect_media, requested_by=user.id)
    db.commit()
    dispatch(job)
    return job


@router.post(
    "/projects/{project_id}/analyze",
    response_model=JobOut,
    dependencies=[Depends(rate_limit("ai-analyze", 20, 3600))],
    responses={503: {"description": "AI is not configured on this server"}},
)
def analyze_project(
    project_id: uuid.UUID,
    body: AnalyzeRequest,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProcessingJob:
    """Transcribe if needed, let the AI pick short-form moments, then create and render clips."""
    if not get_settings().ai_configured:
        raise ServiceUnavailable(
            "AI clip generation is not configured on this server.", code="AI_NOT_CONFIGURED"
        )
    project = get_project(db, user, project_id, lock=True)
    if project.status != ProjectStatus.ready or not project.source_duration_seconds:
        raise Conflict("The video must finish processing before AI can find moments.")
    if active_jobs(db, project.id, JobType.generate_shorts):
        raise Conflict("AI is already working on this video.")
    has_transcript = (
        db.scalar(select(Transcript.id).where(Transcript.project_id == project.id)) is not None
    )
    if not has_transcript:
        summary = usage.summary(db, user)
        needed = usage.minutes(project.source_duration_seconds)
        if needed > summary.ai_minutes_remaining:
            raise QuotaExceeded(
                f"This video needs {needed:.1f} AI minutes; "
                f"{summary.ai_minutes_remaining:.1f} remain this month."
            )
    job = create_job(
        db,
        project=project,
        job_type=JobType.generate_shorts,
        requested_by=user.id,
        params=body.model_dump(),
    )
    db.commit()
    dispatch(job)
    return job
