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
    Transcript,
)
from app.services import usage
from app.services.captions import Cue, build_cues, to_ass
from app.services.jobs import dispatch, transition_job, transition_project
from app.services.media.probe import probe, sniff_container
from app.services.media.render import (
    RenderSpec,
    build_render_command,
    build_thumbnail_command,
    compute_geometry,
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
            follow_up = _queue_auto_shorts(db, project)
            db.commit()
        log.info("inspection complete", extra={"job_id": job_id, "project_id": project_id})
        if follow_up is not None:
            try:
                dispatch(follow_up)
            except Exception:  # noqa: BLE001 - recovery sweep re-dispatches queued jobs
                log.warning("auto shorts dispatch failed", extra={"job_id": follow_up.id})
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
        caption_cues: list[Cue] = []
        caption_position = (clip.render_settings or {}).get("caption_position", "lower")
        if (clip.render_settings or {}).get("captions"):
            transcript = db.scalar(select(Transcript).where(Transcript.project_id == project.id))
            if transcript is not None:
                caption_cues = build_cues(transcript.segments, spec.start, spec.end)
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
            subtitles: Path | None = None
            if caption_cues:
                geo = compute_geometry(spec)
                subtitles = Path(tmp) / "captions.ass"
                subtitles.write_text(
                    to_ass(caption_cues, geo.out_w, geo.out_h, caption_position), encoding="utf-8"
                )
            reporter.stage("rendering", 0.05)
            run_ffmpeg(
                build_render_command(spec, source_input, out, subtitles),
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


# ---------------------------------------------------------------------------
# AI shorts: transcribe -> pick moments -> create clips -> render
# ---------------------------------------------------------------------------

AI_PROJECT_STATES = (ProjectStatus.transcribing, ProjectStatus.analyzing, ProjectStatus.generating)


def _queue_auto_shorts(db: Session, project: Project) -> ProcessingJob | None:
    """Create the AI job requested at upload time (if AI is configured)."""
    from app.services.jobs import create_job

    wanted = (project.processing_settings or {}).get("auto_shorts")
    if not wanted or not get_settings().ai_configured:
        return None
    settings = dict(project.processing_settings)
    settings.pop("auto_shorts", None)  # one-shot request
    project.processing_settings = settings
    return create_job(
        db,
        project=project,
        job_type="generate_shorts",
        requested_by=project.owner_id,
        params=dict(wanted),
        idempotency_key=f"auto-shorts:{project.id}:{project.source_storage_key}",
    )


def _extract_audio(source_input: str, dest: Path, timeout: int) -> None:
    run_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            source_input,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "32k",
            str(dest),
        ],
        timeout=timeout,
    )


def _audio_chunk(audio: Path, start: float, length: float, dest: Path) -> None:
    run_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(audio),
            "-t",
            f"{length:.3f}",
            "-c",
            "copy",
            str(dest),
        ],
        timeout=300,
    )


def _set_project_status(project_id: uuid.UUID, status: str) -> None:
    with _session() as db:
        project = db.get(Project, project_id, with_for_update=True)
        if project is not None and project.status != status:
            transition_project(project, status)
            db.commit()


def generate_shorts_job(job_id: uuid.UUID) -> None:
    from app.services.ai import get_ai_provider
    from app.services.ai.clip_selection import validate_candidates
    from app.services.ai.types import AnalysisRequest, TranscriptSegment

    settings = get_settings()
    storage = get_storage()
    with _session() as db:
        job = _claim(db, job_id, "generate_shorts")
        if job is None:
            return
        project = db.get(Project, job.project_id, with_for_update=True)
        assert project is not None
        params = dict(job.params or {})
        request = AnalysisRequest(
            target_seconds=60 if int(params.get("target_seconds", 30)) >= 60 else 30,
            count=min(max(int(params.get("count", 3)), 1), 5),
            instructions=(params.get("instructions") or None),
        )
        auto_render = bool(params.get("auto_render", True))
        captions = bool(params.get("captions", True))
        language = params.get("language") or None
        transcript = db.scalar(select(Transcript).where(Transcript.project_id == project.id))
        existing_segments = (
            list(transcript.segments) if transcript and transcript.segments else None
        )
        project_id, owner_id, workspace_id = project.id, project.owner_id, project.workspace_id
        source_key, duration = (
            project.source_storage_key,
            float(project.source_duration_seconds or 0),
        )
        owner = db.get(Profile, owner_id)
        assert owner is not None
        ai_limit = get_plan(owner.plan_code).monthly_ai_minutes
        transition_project(
            project, ProjectStatus.analyzing if existing_segments else ProjectStatus.transcribing
        )
        db.commit()

    reporter = JobReporter(job_id)
    try:
        if not source_key or duration <= 0:
            raise ProcessingError("NO_SOURCE", "This project has no processed video.")
        provider = get_ai_provider()

        # 1. Transcript (reused when one already exists, e.g. after edits)
        if existing_segments is None:
            with _session() as db:
                needed = usage.minutes(duration)
                remaining = ai_limit - usage.used(db, owner_id, usage.AI_MINUTES)
                if needed > remaining:
                    raise ProcessingError(
                        "QUOTA_EXCEEDED",
                        f"This video needs {needed:.1f} AI minutes but only "
                        f"{max(remaining, 0):.1f} remain this month.",
                    )
            reporter.stage("extracting_audio", 0.03)
            segments: list[TranscriptSegment] = []
            detected: str | None = None
            with tempfile.TemporaryDirectory(dir=_work_dir()) as tmp:
                audio = Path(tmp) / "audio.mp3"
                _extract_audio(
                    storage.ffmpeg_input(source_key, ttl=3600),
                    audio,
                    settings.ffmpeg_timeout_seconds,
                )
                chunk = float(settings.transcription_chunk_seconds)
                starts = [
                    i * chunk
                    for i in range(int(duration // chunk) + 1)
                    if i * chunk < duration - 0.5
                ] or [0.0]
                for n, start in enumerate(starts):
                    if reporter.cancelled():
                        raise ProcessingError("CANCELLED", "The job was cancelled.")
                    reporter.stage("transcribing", 0.05 + 0.6 * n / len(starts))
                    length = min(chunk, duration - start)
                    part = Path(tmp) / f"chunk{n}.mp3"
                    _audio_chunk(audio, start, length, part)
                    lang, chunk_segments = provider.transcribe_chunk(
                        part, length, language or detected
                    )
                    detected = detected or lang
                    for s in chunk_segments:
                        segments.append(
                            TranscriptSegment(
                                round(s.start + start, 2),
                                round(min(s.end + start, duration), 2),
                                s.text,
                            )
                        )
            with _session() as db:
                row = db.scalar(select(Transcript).where(Transcript.project_id == project_id))
                if row is None:
                    row = Transcript(project_id=project_id)
                    db.add(row)
                row.language = detected
                row.provider = provider.name
                row.has_word_timestamps = False
                row.segments = [s.to_dict() for s in segments]
                row.full_text = " ".join(s.text for s in segments)
                usage.charge_once(
                    db,
                    user_id=owner_id,
                    workspace_id=workspace_id,
                    event_type="ai_transcription",
                    quantity=usage.minutes(duration),
                    unit=usage.AI_MINUTES,
                    idempotency_key=f"transcribe:{project_id}:{source_key}",
                    project_id=project_id,
                    job_id=job_id,
                    metadata={"duration_seconds": duration, "provider": provider.name},
                )
                db.commit()
            _set_project_status(project_id, ProjectStatus.analyzing)
        else:
            segments = [
                TranscriptSegment(float(s["start"]), float(s["end"]), str(s["text"]))
                for s in existing_segments
            ]
            with _session() as db:
                row = db.scalar(select(Transcript).where(Transcript.project_id == project_id))
                detected = row.language if row else None

        if not segments:
            raise ProcessingError(
                "NO_SPEECH",
                "No speech was found in this video, so AI can't pick moments. "
                "You can still create clips manually.",
            )

        # 2. Pick moments
        reporter.stage("finding_moments", 0.7)
        raw = provider.propose_clips(segments, request)
        candidates = validate_candidates(raw, segments, duration, request, detected)
        if not candidates:
            raise ProcessingError(
                "NO_CANDIDATES",
                "The AI couldn't find a self-contained moment of the requested "
                "length. Try the other length or create a clip manually.",
                retryable=False,
            )

        # 3. Create clips and queue renders
        reporter.stage("creating_clips", 0.9)
        _set_project_status(project_id, ProjectStatus.generating)
        render_jobs: list[ProcessingJob] = []
        from app.services.jobs import create_job

        with _session() as db:
            job = db.get(ProcessingJob, job_id, with_for_update=True)
            project = db.get(Project, project_id, with_for_update=True)
            assert job is not None and project is not None
            if job.cancel_requested:
                raise ProcessingError("CANCELLED", "The job was cancelled.")
            render_budget = (
                get_plan(owner.plan_code).monthly_render_minutes
                - usage.used(db, owner_id, usage.RENDER_MINUTES)
                - usage.reserved_render_minutes(db, owner_id)
            )
            for c in candidates:
                clip = Clip(
                    project_id=project_id,
                    title=c.title[:200],
                    start_seconds=c.start_time_seconds,
                    end_seconds=c.end_time_seconds,
                    duration_seconds=c.duration_seconds,
                    selection_reason=c.selection_reason,
                    engagement_score=c.estimated_engagement_score,
                    origin="ai",
                    transcript_excerpt=c.transcript_excerpt,
                    status=ClipStatus.draft,
                    render_settings={
                        "aspect_ratio": "9:16",
                        "fit": "crop",
                        "crop_x": 0.5,
                        "crop_y": 0.5,
                        "pad_color": "black",
                        "normalize_audio": True,
                        "captions": captions,
                        "caption_position": "lower",
                    },
                )
                db.add(clip)
                db.flush()
                cost = usage.minutes(c.duration_seconds)
                if auto_render and cost <= render_budget:
                    render_budget -= cost
                    clip.status = ClipStatus.queued
                    render_jobs.append(
                        create_job(
                            db,
                            project=project,
                            job_type="render_clip",
                            requested_by=owner_id,
                            clip_id=clip.id,
                            params={
                                "start": clip.start_seconds,
                                "end": clip.end_seconds,
                                "auto": True,
                            },
                        )
                    )
            job.params = {
                **job.params,
                "clips_created": len(candidates),
                "renders_queued": len(render_jobs),
            }
            transition_project(project, ProjectStatus.ready)
            transition_job(job, JobStatus.succeeded)
            job.stage = "completed"
            db.commit()
        for rj in render_jobs:
            try:
                dispatch(rj)
            except Exception:  # noqa: BLE001
                log.warning("render dispatch failed; recovery will retry", extra={"job_id": rj.id})
        log.info("ai shorts created", extra={"job_id": job_id, "project_id": project_id})
    except Exception as exc:  # noqa: BLE001

        def _restore(db: Session, job: ProcessingJob) -> None:
            # The source video is still fine: return the project to "ready".
            project = db.get(Project, job.project_id, with_for_update=True)
            if project is not None and project.status in AI_PROJECT_STATES:
                transition_project(project, ProjectStatus.ready)

        _handle_failure(job_id, exc, _restore)
        # A retry will be scheduled for transient errors; keep the project usable meanwhile.
        with _session() as db:
            job = db.get(ProcessingJob, job_id)
            project = db.get(Project, project_id, with_for_update=True)
            if (
                job is not None
                and job.status == JobStatus.queued
                and project is not None
                and project.status in AI_PROJECT_STATES
            ):
                transition_project(project, ProjectStatus.ready)
                db.commit()


@celery_app.task(name="virello.generate_shorts")
def generate_shorts(job_id: str) -> None:
    generate_shorts_job(uuid.UUID(job_id))


# ---------------------------------------------------------------------------
# YouTube link import
# ---------------------------------------------------------------------------


def import_url_job(job_id: uuid.UUID) -> None:
    from app.services.importers.youtube import get_importer
    from app.services.jobs import create_job

    settings = get_settings()
    storage = get_storage()
    with _session() as db:
        job = _claim(db, job_id, "import_url")
        if job is None:
            return
        project = db.get(Project, job.project_id)
        assert project is not None
        source = dict((project.processing_settings or {}).get("import") or {})
        video_id = str(source.get("video_id") or "")
        project_id, owner_id, title_is_placeholder = (
            project.id,
            project.owner_id,
            bool(source.get("placeholder_title")),
        )
        owner = db.get(Profile, owner_id)
        assert owner is not None
        plan = get_plan(owner.plan_code)
        max_duration = min(plan.max_video_duration_seconds, settings.max_video_duration_seconds)
        max_bytes = min(plan.max_upload_bytes, settings.max_upload_bytes)

    reporter = JobReporter(job_id)
    importer = get_importer()
    try:
        if not settings.youtube_import_enabled:
            raise ProcessingError("URL_IMPORT_DISABLED", "YouTube import is turned off.")
        if not video_id:
            raise ProcessingError("NO_SOURCE", "This project has no YouTube link.")

        reporter.stage("fetching_info", 0.02)
        info = importer.fetch_info(video_id)
        if info.is_live:
            raise ProcessingError(
                "LIVE_NOT_SUPPORTED", "Live streams can't be imported. Try again after it ends."
            )
        if not info.duration:
            raise ProcessingError("INVALID_DURATION", "YouTube didn't report this video's length.")
        if info.duration > max_duration:
            raise ProcessingError(
                "VIDEO_TOO_LONG",
                f"The video is {info.duration / 60:.1f} minutes long; your plan allows up to "
                f"{max_duration / 60:.0f} minutes per video.",
            )
        with _session() as db:
            needed = usage.minutes(info.duration)
            remaining = plan.monthly_source_minutes - usage.used(db, owner_id, usage.SOURCE_MINUTES)
            if needed > remaining:
                raise ProcessingError(
                    "QUOTA_EXCEEDED",
                    f"This video needs {needed:.1f} source minutes but only "
                    f"{max(remaining, 0):.1f} remain this month.",
                )
            project = db.get(Project, project_id, with_for_update=True)
            assert project is not None
            if title_is_placeholder:
                project.title = info.title
            project.processing_settings = {
                **project.processing_settings,
                "import": {
                    **source,
                    "title": info.title,
                    "uploader": info.uploader,
                    "duration": info.duration,
                },
            }
            db.commit()

        reporter.stage("downloading", 0.05)
        with tempfile.TemporaryDirectory(dir=_work_dir()) as tmp:
            path = importer.download(
                video_id,
                Path(tmp),
                max_bytes,
                on_progress=reporter.progress("downloading", 0.05, 0.85),
                should_cancel=reporter.cancelled,
            )
            size = path.stat().st_size
            if size > max_bytes:
                raise ProcessingError(
                    "FILE_TOO_LARGE", "The video is larger than your plan's upload limit."
                )
            with path.open("rb") as fh:
                mime = sniff_container(fh.read(64))
            if mime is None:
                raise ProcessingError(
                    "UNSUPPORTED_MEDIA", "The downloaded file isn't a supported video."
                )
            reporter.stage("saving", 0.92)
            key = f"{project_prefix(owner_id, project_id)}source/{uuid.uuid4()}{path.suffix}"
            storage.upload_file(path, key, mime)

        with _session() as db:
            job = db.get(ProcessingJob, job_id, with_for_update=True)
            project = db.get(Project, project_id, with_for_update=True)
            assert job is not None and project is not None
            if job.cancel_requested:
                storage.delete(key)
                raise ProcessingError("CANCELLED", "The job was cancelled.")
            project.source_storage_key = key
            project.source_filename = f"{(project.title or 'youtube')[:180]}{path.suffix}"
            project.source_size_bytes = size
            project.source_mime_type = mime
            db.add(
                MediaAsset(
                    project_id=project_id,
                    job_id=job_id,
                    asset_type=AssetType.source_video,
                    storage_key=key,
                    mime_type=mime,
                    size_bytes=size,
                )
            )
            transition_project(project, ProjectStatus.queued)
            inspect = create_job(
                db,
                project=project,
                job_type="inspect_media",
                requested_by=owner_id,
                idempotency_key=f"inspect-import:{job_id}",
            )
            transition_job(job, JobStatus.succeeded)
            job.stage = "completed"
            db.commit()
        log.info("youtube import complete", extra={"job_id": job_id, "project_id": project_id})
        try:
            dispatch(inspect)
        except Exception:  # noqa: BLE001 - recovery sweep re-dispatches queued jobs
            log.warning("inspect dispatch failed", extra={"job_id": inspect.id})
    except Exception as exc:  # noqa: BLE001

        def _fail(db: Session, job: ProcessingJob) -> None:
            project = db.get(Project, job.project_id, with_for_update=True)
            if project is not None and project.status == ProjectStatus.importing:
                transition_project(
                    project,
                    ProjectStatus.cancelled
                    if job.status == JobStatus.cancelled
                    else ProjectStatus.failed,
                )

        _handle_failure(job_id, exc, _fail)


@celery_app.task(name="virello.import_url")
def import_url(job_id: str) -> None:
    import_url_job(uuid.UUID(job_id))
