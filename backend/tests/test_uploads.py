from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient


def _project(client: TestClient, auth: dict[str, str]) -> str:
    return client.post("/api/v1/projects", json={"title": "Upload"}, headers=auth).json()["id"]


def _initiate(client, auth, pid, **overrides):
    body = {"filename": "talk.mp4", "content_type": "video/mp4", "size_bytes": 1000, **overrides}
    return client.post(f"/api/v1/projects/{pid}/uploads/initiate", json=body, headers=auth)


def test_rejects_unsupported_extension(client: TestClient, auth: dict[str, str]) -> None:
    pid = _project(client, auth)
    for name in ["notes.txt", "clip.avi", "archive.mp4.exe", "noext"]:
        resp = _initiate(client, auth, pid, filename=name)
        assert resp.status_code == 422, name
        assert resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA"


def test_rejects_file_over_plan_limit(client: TestClient, auth: dict[str, str]) -> None:
    resp = _initiate(client, auth, _project(client, auth), size_bytes=50 * 1024**3)
    assert resp.status_code == 402 and resp.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_non_video_content_rejected_on_complete(client: TestClient, auth: dict[str, str]) -> None:
    pid = _project(client, auth)
    payload = b"<html>definitely not a video</html>" * 10
    target = _initiate(client, auth, pid, size_bytes=len(payload)).json()
    assert (
        client.put(
            target["url"].replace("http://testserver", ""),
            content=payload,
            headers=target["headers"],
        ).status_code
        == 200
    )
    resp = client.post(
        f"/api/v1/projects/{pid}/uploads/complete",
        json={"upload_id": target["upload_id"]},
        headers=auth,
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA"
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["status"] == "draft"


def test_incomplete_upload_rejected(
    client: TestClient, auth: dict[str, str], sample_video: Path
) -> None:
    pid = _project(client, auth)
    data = sample_video.read_bytes()
    target = _initiate(client, auth, pid, size_bytes=len(data)).json()
    client.put(
        target["url"].replace("http://testserver", ""),
        content=data[:1000],
        headers=target["headers"],
    )
    resp = client.post(
        f"/api/v1/projects/{pid}/uploads/complete",
        json={"upload_id": target["upload_id"]},
        headers=auth,
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "UPLOAD_INCOMPLETE"


def test_upload_larger_than_signed_size_rejected(client: TestClient, auth: dict[str, str]) -> None:
    pid = _project(client, auth)
    target = _initiate(client, auth, pid, size_bytes=10).json()
    resp = client.put(
        target["url"].replace("http://testserver", ""),
        content=b"x" * 100,
        headers=target["headers"],
    )
    assert resp.status_code == 422


def test_complete_without_upload(client: TestClient, auth: dict[str, str]) -> None:
    pid = _project(client, auth)
    target = _initiate(client, auth, pid).json()
    resp = client.post(
        f"/api/v1/projects/{pid}/uploads/complete",
        json={"upload_id": target["upload_id"]},
        headers=auth,
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "UPLOAD_MISSING"


def test_signed_url_tampering_and_expiry(client: TestClient, auth: dict[str, str]) -> None:
    from app.services.storage import get_storage

    pid = _project(client, auth)
    target = _initiate(client, auth, pid).json()
    url = target["url"].replace("http://testserver", "")
    tampered = url[:-4] + ("0000" if not url.endswith("0000") else "1111")
    assert client.put(tampered, content=b"x", headers=target["headers"]).status_code == 403

    storage = get_storage()
    token = storage.sign(
        {
            "op": "put",
            "key": "users/x/a.mp4",
            "exp": time.time() - 1,  # type: ignore[attr-defined]
            "max": 10,
            "ct": "video/mp4",
        }
    )
    resp = client.put(
        f"/api/v1/storage/local/upload?token={token}",
        content=b"x",
        headers={"Content-Type": "video/mp4"},
    )
    assert resp.status_code == 403
    # A download token cannot be used to upload, and vice versa
    get_token = storage.sign(
        {
            "op": "get",
            "key": "users/x/a.mp4",  # type: ignore[attr-defined]
            "exp": time.time() + 60,
        }
    )
    assert (
        client.put(
            f"/api/v1/storage/local/upload?token={get_token}",
            content=b"x",
            headers={"Content-Type": "video/mp4"},
        ).status_code
        == 403
    )


def test_abort_upload_returns_to_draft(client: TestClient, auth: dict[str, str]) -> None:
    pid = _project(client, auth)
    _initiate(client, auth, pid)
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["status"] == "uploading"
    resp = client.post(f"/api/v1/projects/{pid}/uploads/abort", headers=auth)
    assert resp.status_code == 200 and resp.json()["status"] == "draft"


def test_cannot_upload_twice(client: TestClient, auth: dict[str, str], sample_video: Path) -> None:
    from tests.conftest import upload_video

    pid = upload_video(client, auth, sample_video)["project"]["id"]
    assert _initiate(client, auth, pid).status_code == 409


def test_corrupted_video_fails_with_safe_error(
    client: TestClient, auth: dict[str, str], sample_video: Path
) -> None:
    pid = _project(client, auth)
    # Valid MP4 signature, garbage body: passes sniffing, fails ffprobe.
    data = sample_video.read_bytes()[:32] + b"\x00garbage" * 2000
    target = _initiate(client, auth, pid, size_bytes=len(data)).json()
    client.put(
        target["url"].replace("http://testserver", ""), content=data, headers=target["headers"]
    )
    done = client.post(
        f"/api/v1/projects/{pid}/uploads/complete",
        json={"upload_id": target["upload_id"]},
        headers=auth,
    )
    assert done.status_code == 200
    project = client.get(f"/api/v1/projects/{pid}", headers=auth).json()
    assert project["status"] == "failed"
    job = project["latest_job"]
    assert job["status"] == "failed" and job["error_code"] == "UNREADABLE_MEDIA"
    assert "/" not in job["safe_error_message"]  # no file paths leak
    # Nothing charged for a failed job
    assert client.get("/api/v1/usage", headers=auth).json()["source_minutes_used"] == 0
