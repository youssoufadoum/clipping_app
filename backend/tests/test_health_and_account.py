from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import upload_video


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_ready_reports_without_secrets(client: TestClient) -> None:
    resp = client.get("/ready")
    body = resp.json()
    assert set(body["checks"]) == {"database", "queue", "storage", "ffmpeg"}
    assert body["checks"]["database"] is True
    assert body["checks"]["queue"] is False  # tests point Redis at an unused port
    assert resp.status_code == 503
    assert "postgresql" not in resp.text and "redis://" not in resp.text


def test_metrics_requires_token(client: TestClient) -> None:
    assert client.get("/metrics").status_code == 403
    resp = client.get("/metrics", headers={"Authorization": "Bearer metrics-test-token"})
    assert resp.status_code == 200 and "virello_jobs" in resp.text


def test_openapi_lists_v1_routes(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    for p in [
        "/api/v1/projects",
        "/api/v1/projects/{project_id}/uploads/initiate",
        "/api/v1/clips/{clip_id}/render",
        "/api/v1/jobs/{job_id}",
        "/api/v1/usage",
    ]:
        assert p in paths


def test_errors_have_correlation_ids(client: TestClient) -> None:
    resp = client.get("/api/v1/me")
    assert resp.headers["X-Correlation-ID"]
    assert resp.json()["error"]["correlation_id"] == resp.headers["X-Correlation-ID"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_profile_update_and_onboarding(client: TestClient, auth: dict[str, str]) -> None:
    resp = client.patch(
        "/api/v1/me",
        headers=auth,
        json={
            "display_name": "Ada",
            "creator_type": "podcaster",
            "main_platform": "youtube",
            "onboarding_completed": True,
        },
    )
    assert resp.status_code == 200 and resp.json()["onboarding_completed"] is True
    bad = client.patch("/api/v1/me", headers=auth, json={"avatar_url": "javascript:alert(1)"})
    assert bad.status_code == 422


def test_account_deletion_removes_everything(
    client: TestClient, auth: dict[str, str], sample_video: Path
) -> None:
    from app.services.storage import get_storage

    pid = upload_video(client, auth, sample_video)["project"]["id"]
    root = get_storage().root  # type: ignore[attr-defined]
    assert any(pid in str(p) for p in root.rglob("*"))
    assert client.request("DELETE", "/api/v1/me", headers=auth, json={}).status_code == 422
    assert (
        client.request("DELETE", "/api/v1/me", headers=auth, json={"confirm": "DELETE"}).status_code
        == 204
    )
    assert not any(pid in str(p) for p in root.rglob("*"))
    # The token still verifies cryptographically, but the local account is gone; a new
    # empty profile would be created, with no access to the old project.
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).status_code == 404


def test_cli_set_plan(client: TestClient, auth: dict[str, str]) -> None:
    from app.cli import main

    email = client.get("/api/v1/me", headers=auth).json()["email"]
    assert main(["set-plan", email, "nope"]) == 2
    assert main(["set-plan", "missing@example.com", "pro"]) == 1
    assert main(["set-plan", email, "creator"]) == 0
    usage = client.get("/api/v1/usage", headers=auth).json()
    assert usage["plan"]["code"] == "creator" and usage["plan"]["watermark"] is False
