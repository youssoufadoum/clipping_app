from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.core.errors import Conflict, ProcessingError
from app.models import JobStatus, ProcessingJob, Project, ProjectStatus, UsageLedger
from app.services import usage
from app.services.jobs import transition_job, transition_project
from tests.conftest import upload_video


def test_job_state_machine() -> None:
    job = ProcessingJob(status=JobStatus.queued)
    transition_job(job, JobStatus.running)
    assert job.started_at is not None
    transition_job(job, JobStatus.succeeded)
    assert job.progress == 1.0 and job.completed_at is not None
    with pytest.raises(Conflict):
        transition_job(job, JobStatus.running)
    failed = ProcessingJob(status=JobStatus.failed)
    with pytest.raises(Conflict):
        transition_job(failed, JobStatus.succeeded)


def test_project_state_machine() -> None:
    p = Project(status=ProjectStatus.draft)
    with pytest.raises(Conflict):
        transition_project(p, ProjectStatus.ready)
    for s in (
        ProjectStatus.uploading,
        ProjectStatus.queued,
        ProjectStatus.inspecting,
        ProjectStatus.ready,
    ):
        transition_project(p, s)
    assert p.status == "ready"


def test_render_quota_enforced(
    client: TestClient, auth: dict[str, str], sample_video: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import plans

    pid = upload_video(client, auth, sample_video)["project"]["id"]
    monkeypatch.setitem(plans.PLANS, "free", replace(plans.PLANS["free"], monthly_render_minutes=0))
    cid = client.post(
        f"/api/v1/projects/{pid}/clips",
        headers=auth,
        json={"title": "x", "start_seconds": 0, "end_seconds": 5},
    ).json()["id"]
    resp = client.post(f"/api/v1/clips/{cid}/render", headers=auth)
    assert resp.status_code == 402 and resp.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_source_minutes_quota_enforced_after_probe(
    client: TestClient,
    auth: dict[str, str],
    sample_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import plans

    monkeypatch.setitem(
        plans.PLANS, "free", replace(plans.PLANS["free"], max_video_duration_seconds=5)
    )
    result = upload_video(client, auth, sample_video)
    project = client.get(f"/api/v1/projects/{result['project']['id']}", headers=auth).json()
    assert project["status"] == "failed"
    assert project["latest_job"]["error_code"] == "VIDEO_TOO_LONG"


def test_reserved_render_minutes(
    client: TestClient,
    auth: dict[str, str],
    sample_video: Path,
    defer_tasks: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_resp = None
    monkeypatch.delenv("VIRELLO_TEST_DEFER_TASKS")  # process the upload synchronously
    pid_resp = upload_video(client, auth, sample_video)
    monkeypatch.setenv("VIRELLO_TEST_DEFER_TASKS", "1")  # leave renders queued
    pid = pid_resp["project"]["id"]
    from app.core import plans

    monkeypatch.setitem(plans.PLANS, "free", replace(plans.PLANS["free"], monthly_render_minutes=1))
    ids = [
        client.post(
            f"/api/v1/projects/{pid}/clips",
            headers=auth,
            json={"title": f"c{i}", "start_seconds": 0, "end_seconds": 6},
        ).json()["id"]
        for i in range(3)
    ]
    assert client.post(f"/api/v1/clips/{ids[0]}/render", headers=auth).status_code == 200
    # 0.1 (6s) reserved by the queued job... allow until the reservation reaches the limit
    usage_now = client.get("/api/v1/usage", headers=auth).json()
    assert usage_now["render_minutes_reserved"] == 0.1
    # The same clip cannot be queued twice
    assert client.post(f"/api/v1/clips/{ids[0]}/render", headers=auth).status_code == 409


def test_charge_once_is_idempotent(db, client: TestClient, auth: dict[str, str]) -> None:
    me = client.get("/api/v1/me", headers=auth).json()
    uid = uuid.UUID(me["id"])
    for _ in range(3):
        usage.charge_once(
            db,
            user_id=uid,
            workspace_id=None,
            event_type="test",
            quantity=1.5,
            unit=usage.RENDER_MINUTES,
            idempotency_key="k1",
        )
    db.commit()
    count = db.scalar(select(func.count(UsageLedger.id)).where(UsageLedger.user_id == uid))
    assert count == 1
    assert usage.used(db, uid, usage.RENDER_MINUTES) == 1.5


def test_minutes_rounding() -> None:
    assert usage.minutes(1) == 0.1
    assert usage.minutes(6) == 0.1
    assert usage.minutes(6.01) == 0.2
    assert usage.minutes(60) == 1.0


def test_cancel_queued_job_and_retry(
    client: TestClient,
    auth: dict[str, str],
    sample_video: Path,
    defer_tasks: None,
    eager_queue: list,
) -> None:
    result = upload_video(client, auth, sample_video)
    job = result["job"]
    assert job["status"] == "queued"
    assert eager_queue[-1] == ("virello.inspect_media", [job["id"]])

    cancelled = client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=auth).json()
    assert cancelled["status"] == "cancelled"
    pid = result["project"]["id"]
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["status"] == "cancelled"
    assert client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=auth).status_code == 409

    retried = client.post(f"/api/v1/jobs/{job['id']}/retry", headers=auth)
    assert retried.status_code == 200
    new_id = retried.json()["id"]
    assert new_id != job["id"]
    # Run the deferred task now; the old cancelled job's delivery is a no-op.
    from app.worker.tasks import inspect_media_job

    inspect_media_job(uuid.UUID(job["id"]))
    inspect_media_job(uuid.UUID(new_id))
    project = client.get(f"/api/v1/projects/{pid}", headers=auth).json()
    assert project["status"] == "ready"


def test_duplicate_delivery_is_idempotent(
    client: TestClient, auth: dict[str, str], sample_video: Path, db
) -> None:
    result = upload_video(client, auth, sample_video)
    from app.worker.tasks import inspect_media_job

    inspect_media_job(uuid.UUID(result["job"]["id"]))  # second delivery
    job = db.get(ProcessingJob, uuid.UUID(result["job"]["id"]))
    assert job.status == "succeeded" and job.attempt_count == 1
    assert db.scalar(select(func.count(UsageLedger.id))) == 1


def test_upload_complete_is_idempotent(
    client: TestClient, auth: dict[str, str], sample_video: Path
) -> None:
    result = upload_video(client, auth, sample_video)
    pid = result["project"]["id"]
    # Replaying the same completion returns the same job rather than starting another.
    from app.db.session import get_sessionmaker
    from app.models import ProcessingJob as PJ  # noqa: F401

    with get_sessionmaker()() as s:
        upload_id = s.get(PJ, uuid.UUID(result["job"]["id"])).idempotency_key.split(":")[1]
    replay = client.post(
        f"/api/v1/projects/{pid}/uploads/complete", json={"upload_id": upload_id}, headers=auth
    )
    assert replay.status_code == 200 and replay.json()["job"]["id"] == result["job"]["id"]


def test_retryable_failure_is_retried_then_fails(
    client: TestClient,
    auth: dict[str, str],
    sample_video: Path,
    monkeypatch: pytest.MonkeyPatch,
    eager_queue: list,
) -> None:
    from app.worker import tasks

    real_run = tasks.run_ffmpeg
    broken = {"on": True}

    def boom(*args, **kwargs):
        if broken["on"]:
            raise ProcessingError("RENDER_FAILED", "Video rendering failed.", retryable=True)
        return real_run(*args, **kwargs)

    pid = upload_video(client, auth, sample_video)["project"]["id"]
    cid = client.post(
        f"/api/v1/projects/{pid}/clips",
        headers=auth,
        json={"title": "x", "start_seconds": 0, "end_seconds": 2},
    ).json()["id"]
    monkeypatch.setattr(tasks, "run_ffmpeg", boom)
    job = client.post(f"/api/v1/clips/{cid}/render", headers=auth).json()
    state = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert state["status"] == "failed"
    assert state["attempt_count"] == state["max_attempts"] == 3
    assert state["error_code"] == "RENDER_FAILED"
    assert client.get(f"/api/v1/clips/{cid}", headers=auth).json()["status"] == "failed"
    # Retry after the transient problem is gone succeeds and the source is untouched.
    broken["on"] = False
    retry = client.post(f"/api/v1/jobs/{job['id']}/retry", headers=auth).json()
    assert client.get(f"/api/v1/jobs/{retry['id']}", headers=auth).json()["status"] == "succeeded"
    assert client.get("/api/v1/usage", headers=auth).json()["render_minutes_used"] == 0.1


def test_stale_running_job_recovered(
    client: TestClient, auth: dict[str, str], sample_video: Path, db, defer_tasks: None
) -> None:
    from app.worker.tasks import recover_stale_jobs_once

    result = upload_video(client, auth, sample_video)
    jid = uuid.UUID(result["job"]["id"])
    old = datetime.now(UTC) - timedelta(hours=1)
    db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == jid)
        .values(status="running", attempt_count=1, updated_at=old)
    )
    db.commit()
    stats = recover_stale_jobs_once()
    assert stats["redispatched"] == 1
    db.expire_all()
    assert db.get(ProcessingJob, jid).status == "queued"

    db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == jid)
        .values(status="running", attempt_count=3, updated_at=old)
    )
    db.commit()
    assert recover_stale_jobs_once()["failed"] == 1
    db.expire_all()
    assert db.get(ProcessingJob, jid).error_code == "WORKER_LOST"


def test_unavailable_features_are_explicit(client: TestClient, auth: dict[str, str]) -> None:
    pid = client.post("/api/v1/projects", json={"title": "x"}, headers=auth).json()["id"]
    resp = client.post(f"/api/v1/projects/{pid}/analyze", headers=auth, json={})
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "AI_NOT_CONFIGURED"
    resp = client.post("/api/v1/billing/checkout", headers=auth)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "BILLING_UNAVAILABLE"
    plans = client.get("/api/v1/billing/plans").json()
    assert {p["code"] for p in plans} == {"free", "creator", "pro", "team"}
    assert not any(p["checkout_available"] for p in plans)


def test_queue_unavailable_keeps_job(
    client: TestClient, auth: dict[str, str], sample_video: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.worker.celery_app import celery_app

    def down(*_a, **_k):
        raise ConnectionError("broker down")

    monkeypatch.setattr(celery_app, "send_task", down)
    pid = client.post("/api/v1/projects", json={"title": "q"}, headers=auth).json()["id"]
    data = sample_video.read_bytes()
    target = client.post(
        f"/api/v1/projects/{pid}/uploads/initiate",
        headers=auth,
        json={"filename": "a.mp4", "content_type": "video/mp4", "size_bytes": len(data)},
    ).json()
    client.put(
        target["url"].replace("http://testserver", ""), content=data, headers=target["headers"]
    )
    resp = client.post(
        f"/api/v1/projects/{pid}/uploads/complete",
        headers=auth,
        json={"upload_id": target["upload_id"]},
    )
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "QUEUE_UNAVAILABLE"
    project = client.get(f"/api/v1/projects/{pid}", headers=auth).json()
    assert project["status"] == "queued" and project["latest_job"]["status"] == "queued"
