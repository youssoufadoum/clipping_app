from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "virello", broker=settings.redis_url, backend=None, include=["app.worker.tasks"]
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="media",
    task_serializer="json",
    accept_content=["json"],
    task_time_limit=settings.ffmpeg_timeout_seconds + 300,
    task_soft_time_limit=settings.ffmpeg_timeout_seconds + 120,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": settings.ffmpeg_timeout_seconds + 600},
    worker_hijack_root_logger=False,
    beat_schedule={
        "recover-stale-jobs": {"task": "virello.recover_stale_jobs", "schedule": 60.0},
    },
)
