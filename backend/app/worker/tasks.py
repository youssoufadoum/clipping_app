"""Background processing tasks.

Each task receives only a job id. The job row is the source of truth: tasks
claim it with a row lock, so duplicate deliveries are harmless, and every
outcome (progress, failure reason, retry) is persisted for the UI to poll.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from celery.signals import worker_process_init
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ProcessingError
from app.core.logging import configure_logging
from app.core.plans import get_plan
from app.db.session import get_sessionmaker
from app.models import (
    AssetType,
    Clip,
    ClipStatus,
    JobStatus,
    MediaAsset,
    ProcessingJob,
    Profile,
    Project,
    ProjectStatus,
)
from app.services import usage
from app.services.jobs import dispatch, transition_job, transition_project
from app.services.media.probe import probe, sniff_container
from app.services.media.render import (
    RenderSpec,
    build_render_command,
    build_thumbnail_command,
    run_ffmpeg,
)
from app.services.storage import get_storage, project_prefix
from app.worker.celery_app import celery_app

log = logging.getLogger(__name__)

STALE_RUNNING_AFTER = timedelta(minutes=10)
STALE_QUEUED_AFTER = timedelta(minutes=2)


@worker_process_init.connect
def _init_worker(**_: Any) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn, environment=settings.app_env, send_default_pii=False
        )


def _session() -> Session:
    return get_sessionmaker()()


def _claim(db: Session, job_id: uuid.UUID, job_type: str) -> ProcessingJob | None:
    job = db.get(ProcessingJob, job_id, with_for_update=True)
    if job is None or job.job_type != job_type:
        log.warning("job not found or wrong type", extra={"job_id": job_id})
        return None
    now = datetime.now(UTC)
    stale_running = job.status == JobStatus.running and job.updated_at < now - STALE_RUNNING_AFTER
    if job.status != JobStatus.queued and not stale_running:
        log.info(
            "job already claimed; skipping duplicate delivery",
            extra={"job_id": job_id, "status": job.status},
        )
        return None
    if job.cancel_requested:
        if job.status == JobStatus.queued:
            transition_job(job, JobStatus.cancelled)
        db.commit()
        return None
    if stale_running:
        transition_job(job, JobStatus.queued)
    transition_job(job, JobStatus.running)
    job.attempt_count += 1
    job.error_code = None
    job.safe_error_message = None
    db.commit()
    return job


class JobReporter:
    """Persists progress in short transactions so the UI sees real stage changes."""

    def __init__(self, job_id: uuid.UUID) -> None:
        self.job_id = job_id
        self._last_write = 0.0

    def stage(self, stage: str, progress: float) -> None:
        self._write(stage=stage, progress=progress, force=True)

    def progress(self, stage: str, base: float, span: float) -> Callable[[float], None]:
        def report(fraction: float) -> None:
            self._write(stage=stage, progress=base + span * fraction)

        return report

    def _write(self, *, stage: str, progress: float, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_write < 2.0:
            return
        self._last_write = now
        with _session() as db:
            db.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == self.job_id)
                .values(
                    stage=stage,
                    progress=round(min(max(progress, 0.0), 1.0), 4),
                    updated_at=datetime.now(UTC),
                )
            )
            db.commit()

    def cancelled(self) -> bool:
        with _session() as db:
            return bool(
                db.scalar(
                    select(ProcessingJob.cancel_requested).where(ProcessingJob.id == self.job_id)
                )
            )


def _handle_failure(
    job_id: uuid.UUID, exc: Exception, on_final_failure: Callable[[Session, ProcessingJob], None]
) -> None:
    if isinstance(exc, ProcessingError):
        code, message, retryable = exc.code, exc.safe_message, exc.retryable
    else:
        log.exception("unexpected worker error", extra={"job_id": job_id})
        code, message, retryable = (
            "INTERNAL_ERROR",
            "An unexpected processing error occurred.",
            True,
        )
    with _session() as db:
        job = db.get(ProcessingJob, job_id, with_for_update=True)
        if job is None or job.status != JobStatus.running:
            return
        job.error_code = code
        job.safe_error_message = message
        if code == "CANCELLED":
            transition_job(job, JobStatus.cancelled)
            job.stage = "cancelled"
            on_final_failure(db, job)
            db.commit()
            return
        if retryable and job.attempt_count < job.max_attempts:
            transition_job(job, JobStatus.queued)
            job.stage = "retry_scheduled"
            db.commit()
            delay = 15 * (2 ** (job.attempt_count - 1))
            log.warning("job failed; retrying", extra={"job_id": job_id, "status": code})
            celery_app.send_task(
                f"virello.{job.job_type}", args=[str(job_id)], countdown=delay, queue="media"
            )
            return
        transition_job(job, JobStatus.failed)
        job.stage = "failed"
        on_final_failure(db, job)
        db.commit()
        log.error("job failed permanently", extra={"job_id": job_id, "status": code})


# ---------------------------------------------------------------------------
# Media inspection
# ---------------------------------------------------------------------------


def inspect_media_job(job_id: uuid.UUID) -> None:
    settings = get_settings()
    storage = get_storage()
    with _session() as db:
        job = _claim(db, job_id, "inspect_media")
        if job is None:
            return
        project = db.get(Project, job.project_id, with_for_update=True)
        assert project is not None
        if project.status == ProjectStatus.queued:
            transition_project(project, ProjectStatus.inspecting)
        db.commit()
        source_key, owner_id, project_id = (
            project.source_storage_key,
            project.owner_id,
            project.id,
        )

    reporter = JobReporter(job_id)
    try:
        if not source_key:
            raise ProcessingError("NO_SOURCE", "This project has no uploaded video.")
        reporter.stage("verifying_file", 0.05)
        info_obj = storage.head(source_key)
        if info_obj is None:
            raise ProcessingError("SOURCE_MISSING", "The uploaded file could not be found.")
        mime = sniff_container(storage.read_prefix(source_key, 64))
        if mime is None:
            raise ProcessingError(
                "UNSUPPORTED_MEDIA", "The file is not a supported video (MP4, MOV or WebM)."
            )

        reporter.stage("probing", 0.2)
        source_input = storage.ffmpeg_input(source_key, ttl=900)
        info = probe(source_input)

        with _session() as db:
            owner = db.get(Profile, owner_id)
            assert owner is not None
            plan = get_plan(owner.plan_code)
            max_duration = min(plan.max_video_duration_seconds, settings.max_video_duration_seconds)
            if info.duration > max_duration:
                raise ProcessingError(
                    "VIDEO_TOO_LONG",
                    f"The video is {info.duration / 60:.1f} minutes long; your plan allows up "
                    f"to {max_duration / 60:.0f} minutes per video.",
                )
            needed = usage.minutes(info.duration)
            remaining = plan.monthly_source_minutes - usage.used(db, owner.id, usage.SOURCE_MINUTES)
            if needed > remaining:
                raise ProcessingError(
                    "QUOTA_EXCEEDED",
                    f"This video needs {needed:.1f} source minutes but only "
                    f"{max(remaining, 0):.1f} remain this month.",
                )

        reporter.stage("generating_thumbnail", 0.6)
        with tempfile.TemporaryDirectory(dir=_work_dir()) as tmp:
            thumb = Path(tmp) / "thumb.jpg"
            run_ffmpeg(
                build_thumbnail_command(source_input, thumb, min(info.duration * 0.1, 5.0)),
                timeout=120,
            )
            thumb_key = f"{project_prefix(owner_id, project_id)}thumbnails/source.jpg"
            storage.upload_file(thumb, thumb_key, "image/jpeg")
            thumb_size = thumb.stat().st_size

        reporter.stage("finalizing", 0.9)
        with _session() as db:
            job = db.get(ProcessingJob, job_id, with_for_update=True)
            project = db.get(Project, project_id, with_for_update=True)
            assert job is not None and project is not None
            if job.cancel_requested:
                raise ProcessingError("CANCELLED", "The job was cancelled.")
            project.source_duration_seconds = info.duration
            project.source_width = info.width
            project.source_height = info.height
            project.source_fps = info.fps
            project.source_mime_type = mime
            project.source_size_bytes = info_obj.size
            project.source_metadata = info.summary()
            for old in db.scalars(
                select(MediaAsset).where(
                    MediaAsset.project_id == project_id,
                    MediaAsset.asset_type == AssetType.thumbnail,
                )
            ):
                db.delete(old)
            db.add(
                MediaAsset(
                    project_id=project_id,
                    job_id=job_id,
                    asset_type=AssetType.thumbnail,
                    storage_key=thumb_key,
                    mime_type="image/jpeg",
                    size_bytes=thumb_size,
                )
            )
            source_asset = db.scalar(
                select(MediaAsset).where(
                    MediaAsset.project_id == project_id,
                    MediaAsset.asset_type == AssetType.source_video,
                )
            )
            if source_asset is not None:
                source_asset.duration_seconds = info.duration
                source_asset.width, source_asset.height = info.width, info.height
                source_asset.mime_type = mime
                source_asset.size_bytes = info_obj.size
            usage.charge_once(
                db,
                user_id=project.owner_id,
                workspace_id=project.workspace_id,
                event_type="source_processed",
                quantity=usage.minutes(info.duration),
                unit=usage.SOURCE_MINUTES,
                idempotency_key=f"source:{project_id}:{source_key}",
                project_id=project_id,
                job_id=job_id,
                metadata={"duration_seconds": info.duration},
            )
            transition_project(project, ProjectStatus.ready)
            transition_job(job, JobStatus.succeeded)
            job.stage = "completed"
            db.commit()
        log.info("inspection complete", extra={"job_id": job_id, "project_id": project_id})
    except Exception as exc:  # noqa: BLE001 - normalized in _handle_failure

        def _fail_project(db: Session, job: ProcessingJob) -> None:
            project = db.get(Project, job.project_id, with_for_update=True)
            if project is None:
                return
            target = (
                ProjectStatus.cancelled
                if job.status == JobStatus.cancelled
                else ProjectStatus.failed
            )
            if project.status in (ProjectStatus.inspecting, ProjectStatus.queued):
                transition_project(project, target)

        _handle_failure(job_id, exc, _fail_project)


@celery_app.task(name="virello.inspect_media")
def inspect_media(job_id: str) -> None:
    inspect_media_job(uuid.UUID(job_id))


# ---------------------------------------------------------------------------
# Clip rendering
# ---------------------------------------------------------------------------


def settings_hash(clip: Clip) -> str:
    payload = {"start": clip.start_seconds, "end": clip.end_seconds, "render": clip.render_settings}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def spec_for(clip: Clip, project: Project, watermark: bool) -> RenderSpec:
    rs = clip.render_settings or {}
    meta = project.source_metadata or {}
    return RenderSpec(
        start=clip.start_seconds,
        end=clip.end_seconds,
        source_width=int(project.source_width or 0),
        source_height=int(project.source_height or 0),
        aspect_ratio=rs.get("aspect_ratio", "9:16"),
        fit=rs.get("fit", "crop"),
        crop_x=float(rs.get("crop_x", 0.5)),
        crop_y=float(rs.get("crop_y", 0.5)),
        pad_color=rs.get("pad_color", "black"),
        normalize_audio=bool(rs.get("normalize_audio", False)),
        watermark=watermark,
        has_audio=bool(meta.get("has_audio", True)),
    )


def render_clip_job(job_id: uuid.UUID) -> None:
    settings = get_settings()
    storage = get_storage()
    with _session() as db:
        job = _claim(db, job_id, "render_clip")
        if job is None:
            return
        clip = db.get(Clip, job.clip_id, with_for_update=True) if job.clip_id else None
        project = db.get(Project, job.project_id)
        if clip is None or project is None or not project.source_storage_key:
            transition_job(job, JobStatus.failed)
            job.error_code, job.safe_error_message = "CLIP_MISSING", "The clip no longer exists."
            db.commit()
            return
        owner = db.get(Profile, project.owner_id)
        assert owner is not None
        clip.status = ClipStatus.rendering
        spec = spec_for(clip, project, watermark=get_plan(owner.plan_code).watermark)
        clip_hash = settings_hash(clip)
        db.commit()
        source_key, owner_id, project_id, clip_id = (
            project.source_storage_key,
            project.owner_id,
            project.id,
            clip.id,
        )
        workspace_id = project.workspace_id

    reporter = JobReporter(job_id)
    try:
        reporter.stage("preparing", 0.02)
        source_input = storage.ffmpeg_input(source_key, ttl=settings.ffmpeg_timeout_seconds + 600)
        with tempfile.TemporaryDirectory(dir=_work_dir()) as tmp:
            out = Path(tmp) / "clip.mp4"
            reporter.stage("rendering", 0.05)
            run_ffmpeg(
                build_render_command(spec, source_input, out),
                duration=spec.duration,
                timeout=settings.ffmpeg_timeout_seconds,
                on_progress=reporter.progress("rendering", 0.05, 0.8),
                should_cancel=reporter.cancelled,
            )
            reporter.stage("validating_output", 0.88)
            out_info = probe(out)
            if abs(out_info.duration - spec.duration) > max(1.0, spec.duration * 0.05):
                raise ProcessingError(
                    "OUTPUT_INVALID", "The rendered file failed validation.", retryable=True
                )
            thumb = Path(tmp) / "thumb.jpg"
            run_ffmpeg(
                build_thumbnail_command(out, thumb, min(1.0, out_info.duration / 2)), timeout=120
            )

            reporter.stage("uploading", 0.92)
            base = f"{project_prefix(owner_id, project_id)}clips/{clip_id}/"
            video_key = f"{base}{job_id}.mp4"
            thumb_key = f"{base}{job_id}.jpg"
            storage.upload_file(out, video_key, "video/mp4")
            storage.upload_file(thumb, thumb_key, "image/jpeg")
            video_size, thumb_size = out.stat().st_size, thumb.stat().st_size
            checksum = _sha256(out)

        with _session() as db:
            job = db.get(ProcessingJob, job_id, with_for_update=True)
            clip = db.get(Clip, clip_id, with_for_update=True)
            assert job is not None
            if clip is None:
                storage.delete(video_key)
                storage.delete(thumb_key)
                transition_job(job, JobStatus.failed)
                job.error_code, job.safe_error_message = "CLIP_MISSING", "The clip was deleted."
                db.commit()
                return
            db.add(
                MediaAsset(
                    project_id=project_id,
                    clip_id=clip_id,
                    job_id=job_id,
                    asset_type=AssetType.rendered_clip,
                    storage_key=video_key,
                    mime_type="video/mp4",
                    size_bytes=video_size,
                    duration_seconds=out_info.duration,
                    width=out_info.width,
                    height=out_info.height,
                    checksum=checksum,
                )
            )
            db.add(
                MediaAsset(
                    project_id=project_id,
                    clip_id=clip_id,
                    job_id=job_id,
                    asset_type=AssetType.clip_thumbnail,
                    storage_key=thumb_key,
                    mime_type="image/jpeg",
                    size_bytes=thumb_size,
                )
            )
            usage.charge_once(
                db,
                user_id=owner_id,
                workspace_id=workspace_id,
                event_type="clip_rendered",
                quantity=usage.minutes(out_info.duration),
                unit=usage.RENDER_MINUTES,
                idempotency_key=f"render:{job_id}",
                project_id=project_id,
                job_id=job_id,
                metadata={"clip_id": str(clip_id), "duration_seconds": out_info.duration},
            )
            # The clip may have been edited while rendering; only mark it current if not.
            clip.rendered_settings_hash = clip_hash
            clip.status = ClipStatus.rendered
            transition_job(job, JobStatus.succeeded)
            job.stage = "completed"
            db.commit()
        log.info("render complete", extra={"job_id": job_id, "clip_id": clip_id})
    except Exception as exc:  # noqa: BLE001

        def _fail_clip(db: Session, job: ProcessingJob) -> None:
            clip = db.get(Clip, job.clip_id) if job.clip_id else None
            if clip is not None:
                clip.status = (
                    ClipStatus.failed
                    if job.status == JobStatus.failed
                    else (ClipStatus.rendered if clip.rendered_settings_hash else ClipStatus.draft)
                )

        _handle_failure(job_id, exc, _fail_clip)


@celery_app.task(name="virello.render_clip")
def render_clip(job_id: str) -> None:
    render_clip_job(uuid.UUID(job_id))


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


def recover_stale_jobs_once() -> dict[str, int]:
    """Re-dispatch queued jobs that never started and recover jobs orphaned by a crash."""
    now = datetime.now(UTC)
    redispatched = failed = 0
    with _session() as db:
        stale_queued = list(
            db.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.status == JobStatus.queued,
                    ProcessingJob.updated_at < now - STALE_QUEUED_AFTER,
                )
                .limit(100)
            )
        )
        stale_running = list(
            db.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.status == JobStatus.running,
                    ProcessingJob.updated_at < now - STALE_RUNNING_AFTER,
                )
                .with_for_update(skip_locked=True)
                .limit(100)
            )
        )
        to_dispatch: list[ProcessingJob] = list(stale_queued)
        for job in stale_running:
            if job.attempt_count >= job.max_attempts:
                transition_job(job, JobStatus.failed)
                job.error_code = "WORKER_LOST"
                job.safe_error_message = "Processing was interrupted and could not be completed."
                failed += 1
            else:
                transition_job(job, JobStatus.queued)
                job.stage = "recovered"
                to_dispatch.append(job)
        for job in to_dispatch:
            job.updated_at = now  # back off the next recovery sweep
        db.commit()
        for job in to_dispatch:
            try:
                dispatch(job)
                redispatched += 1
            except Exception:  # noqa: BLE001 - broker down; next sweep retries
                log.warning("re-dispatch failed", extra={"job_id": job.id})
    return {"redispatched": redispatched, "failed": failed}


@celery_app.task(name="virello.recover_stale_jobs")
def recover_stale_jobs() -> dict[str, int]:
    return recover_stale_jobs_once()


def _work_dir() -> str:
    path = Path(get_settings().work_dir)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cleanup_work_dir(max_age_hours: int = 6) -> None:
    root = Path(get_settings().work_dir)
    if not root.exists():
        return
    cutoff = time.time() - max_age_hours * 3600
    for child in root.iterdir():
        if child.stat().st_mtime < cutoff:
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink()
