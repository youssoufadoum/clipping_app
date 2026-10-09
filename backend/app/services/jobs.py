"""Processing job lifecycle: validated state transitions, creation and dispatch."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ServiceUnavailable
from app.models import JobStatus, ProcessingJob, Project, ProjectStatus

log = logging.getLogger(__name__)

JOB_TRANSITIONS: dict[str, set[str]] = {
    JobStatus.queued: {JobStatus.running, JobStatus.cancelled, JobStatus.failed},
    JobStatus.running: {
        JobStatus.succeeded,
        JobStatus.failed,
        JobStatus.cancelled,
        JobStatus.queued,
    },
    JobStatus.failed: set(),
    JobStatus.succeeded: set(),
    JobStatus.cancelled: set(),
}

PROJECT_TRANSITIONS: dict[str, set[str]] = {
    ProjectStatus.draft: {ProjectStatus.uploading, ProjectStatus.archived},
    ProjectStatus.uploading: {
        ProjectStatus.queued,
        ProjectStatus.draft,
        ProjectStatus.failed,
        ProjectStatus.archived,
    },
    ProjectStatus.queued: {ProjectStatus.inspecting, ProjectStatus.failed, ProjectStatus.cancelled},
    ProjectStatus.inspecting: {
        ProjectStatus.ready,
        ProjectStatus.failed,
        ProjectStatus.queued,
        ProjectStatus.cancelled,
    },
    ProjectStatus.ready: {
        ProjectStatus.transcribing,
        ProjectStatus.analyzing,
        ProjectStatus.rendering,
        ProjectStatus.completed,
        ProjectStatus.archived,
    },
    ProjectStatus.transcribing: {
        ProjectStatus.analyzing,
        ProjectStatus.ready,
        ProjectStatus.failed,
        ProjectStatus.cancelled,
    },
    ProjectStatus.analyzing: {
        ProjectStatus.generating,
        ProjectStatus.ready,
        ProjectStatus.failed,
        ProjectStatus.cancelled,
    },
    ProjectStatus.generating: {ProjectStatus.ready, ProjectStatus.failed, ProjectStatus.cancelled},
    ProjectStatus.rendering: {
        ProjectStatus.ready,
        ProjectStatus.completed,
        ProjectStatus.partially_failed,
    },
    ProjectStatus.completed: {ProjectStatus.ready, ProjectStatus.archived},
    ProjectStatus.partially_failed: {ProjectStatus.ready, ProjectStatus.archived},
    ProjectStatus.failed: {ProjectStatus.queued, ProjectStatus.draft, ProjectStatus.archived},
    ProjectStatus.cancelled: {ProjectStatus.queued, ProjectStatus.draft, ProjectStatus.archived},
    ProjectStatus.archived: {ProjectStatus.draft, ProjectStatus.ready, ProjectStatus.failed},
}

ACTIVE_JOB_STATUSES = (JobStatus.queued, JobStatus.running)


def transition_job(job: ProcessingJob, new_status: str) -> None:
    if new_status not in JOB_TRANSITIONS.get(job.status, set()):
        raise Conflict(
            f"Job cannot move from {job.status} to {new_status}.", code="INVALID_JOB_TRANSITION"
        )
    job.status = new_status
    now = datetime.now(UTC)
    if new_status == JobStatus.running:
        job.started_at = now
    if new_status in (JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled):
        job.completed_at = now
    if new_status == JobStatus.succeeded:
        job.progress = 1.0


def transition_project(project: Project, new_status: str) -> None:
    if project.status == new_status:
        return
    if new_status not in PROJECT_TRANSITIONS.get(project.status, set()):
        raise Conflict(
            f"Project cannot move from {project.status} to {new_status}.",
            code="INVALID_PROJECT_TRANSITION",
        )
    project.status = new_status


def active_jobs(
    db: Session,
    project_id: uuid.UUID,
    job_type: str | None = None,
    clip_id: uuid.UUID | None = None,
) -> list[ProcessingJob]:
    stmt = select(ProcessingJob).where(
        ProcessingJob.project_id == project_id,
        ProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
    )
    if job_type:
        stmt = stmt.where(ProcessingJob.job_type == job_type)
    if clip_id:
        stmt = stmt.where(ProcessingJob.clip_id == clip_id)
    return list(db.scalars(stmt))


def create_job(
    db: Session,
    *,
    project: Project,
    job_type: str,
    requested_by: uuid.UUID | None,
    clip_id: uuid.UUID | None = None,
    params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> ProcessingJob:
    if idempotency_key:
        existing = db.scalar(
            select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing
    job = ProcessingJob(
        project_id=project.id,
        clip_id=clip_id,
        requested_by=requested_by,
        job_type=job_type,
        status=JobStatus.queued,
        stage="queued",
        progress=0.0,
        params=params or {},
        idempotency_key=idempotency_key,
    )
    db.add(job)
    db.flush()
    return job


TASK_NAMES = {
    "inspect_media": "virello.inspect_media",
    "render_clip": "virello.render_clip",
    "generate_shorts": "virello.generate_shorts",
}


def dispatch(job: ProcessingJob) -> None:
    """Send a committed job to the queue. Call only after the DB transaction commits."""
    from app.worker.celery_app import celery_app

    task_name = TASK_NAMES.get(job.job_type)
    if task_name is None:
        raise ServiceUnavailable(f"No worker is available for {job.job_type} jobs.")
    try:
        celery_app.send_task(task_name, args=[str(job.id)], queue="media")
    except Exception as exc:  # broker connection errors vary by transport
        log.exception("failed to dispatch job", extra={"job_id": job.id})
        # The job stays queued; the recovery task re-dispatches stale queued jobs.
        raise ServiceUnavailable(
            "The processing queue is temporarily unavailable. Your job is saved and will "
            "start automatically when the queue recovers.",
            code="QUEUE_UNAVAILABLE",
            retryable=True,
        ) from exc
