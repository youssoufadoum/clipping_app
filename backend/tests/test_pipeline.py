"""End-to-end pipeline tests: upload -> inspect -> clip -> render -> download."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.services.media.probe import probe
from tests.conftest import register, upload_video


def _download(client: TestClient, url: str) -> bytes:
    resp = client.get(url.replace("http://testserver", ""))
    assert resp.status_code == 200, resp.text
    return resp.content


def test_upload_inspect_render_download(
    client: TestClient, auth: dict[str, str], sample_video: Path, tmp_path: Path
) -> None:
    result = upload_video(client, auth, sample_video)
    pid = result["project"]["id"]

    project = client.get(f"/api/v1/projects/{pid}", headers=auth).json()
    assert project["status"] == "ready"
    assert project["source_width"] == 640 and project["source_height"] == 360
    assert 11.5 < project["source_duration_seconds"] < 12.5
    assert project["source_mime_type"] == "video/mp4"
    assert project["source_metadata"]["has_audio"] is True
    assert project["latest_job"]["status"] == "succeeded"
    assert project["latest_job"]["progress"] == 1.0
    assert project["thumbnail_url"]
    assert _download(client, project["thumbnail_url"])[:2] == b"\xff\xd8"  # JPEG

    # Source preview URL works and supports range requests (needed for seeking)
    src = client.get(f"/api/v1/projects/{pid}/source-url", headers=auth).json()["url"]
    ranged = client.get(src.replace("http://testserver", ""), headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206 and len(ranged.content) == 100

    clip = client.post(
        f"/api/v1/projects/{pid}/clips",
        headers=auth,
        json={
            "title": "Best moment",
            "start_seconds": 2,
            "end_seconds": 7,
            "render_settings": {"aspect_ratio": "9:16", "crop_x": 0.25},
        },
    )
    assert clip.status_code == 201, clip.text
    cid = clip.json()["id"]
    assert clip.json()["duration_seconds"] == 5

    not_yet = client.get(f"/api/v1/clips/{cid}/download", headers=auth)
    assert not_yet.status_code == 404 and not_yet.json()["error"]["code"] == "NOT_RENDERED"

    job = client.post(f"/api/v1/clips/{cid}/render", headers=auth)
    assert job.status_code == 200, job.text
    job_state = client.get(f"/api/v1/jobs/{job.json()['id']}", headers=auth).json()
    assert job_state["status"] == "succeeded", job_state

    clip_state = client.get(f"/api/v1/clips/{cid}", headers=auth).json()
    assert clip_state["status"] == "rendered" and clip_state["render_is_current"] is True

    dl = client.get(f"/api/v1/clips/{cid}/download", headers=auth).json()
    assert dl["filename"] == "best-moment.mp4"
    resp = client.get(dl["url"].replace("http://testserver", ""))
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    out = tmp_path / "out.mp4"
    out.write_bytes(resp.content)
    info = probe(out)
    assert abs(info.duration - 5.0) < 0.2
    assert info.has_audio and info.video_codec == "h264"
    # 640x360 source cropped to 9:16 without upscaling: 202x360
    assert (info.width, info.height) == (202, 360)

    # Usage was charged exactly once for source and render
    usage = client.get("/api/v1/usage", headers=auth).json()
    assert usage["source_minutes_used"] == 0.2  # 12s rounded up to tenths of a minute
    assert usage["render_minutes_used"] == 0.1
    history = client.get("/api/v1/usage/history", headers=auth).json()
    assert {e["event_type"] for e in history["items"]} == {"source_processed", "clip_rendered"}

    # Editing trim points marks the render as stale and persists
    edited = client.patch(
        f"/api/v1/clips/{cid}", headers=auth, json={"title": "Renamed", "start_seconds": 3}
    )
    assert edited.status_code == 200
    assert edited.json()["render_is_current"] is False
    assert client.get(f"/api/v1/clips/{cid}", headers=auth).json()["title"] == "Renamed"

    exports = client.get("/api/v1/exports", headers=auth).json()
    assert exports["total"] == 1


def test_landscape_and_square_and_pad(
    client: TestClient, auth: dict[str, str], sample_video: Path, tmp_path: Path
) -> None:
    pid = upload_video(client, auth, sample_video)["project"]["id"]
    expected = {
        ("1:1", "crop"): (360, 360),
        ("16:9", "crop"): (640, 360),
        ("9:16", "pad"): (640, 1136),  # full frame at native width, padded
    }
    for (ratio, fit), dims in expected.items():
        cid = client.post(
            f"/api/v1/projects/{pid}/clips",
            headers=auth,
            json={
                "title": f"{ratio} {fit}",
                "start_seconds": 0,
                "end_seconds": 2,
                "render_settings": {"aspect_ratio": ratio, "fit": fit},
            },
        ).json()["id"]
        assert client.post(f"/api/v1/clips/{cid}/render", headers=auth).status_code == 200
        url = client.get(f"/api/v1/clips/{cid}/download", headers=auth).json()["url"]
        out = tmp_path / f"{ratio.replace(':', 'x')}-{fit}.mp4"
        out.write_bytes(_download(client, url))
        info = probe(out)
        assert (info.width, info.height) == dims, (ratio, fit, info.width, info.height)


def test_silent_mov_source(
    client: TestClient, auth: dict[str, str], silent_video: Path, tmp_path: Path
) -> None:
    pid = upload_video(client, auth, silent_video)["project"]["id"]
    project = client.get(f"/api/v1/projects/{pid}", headers=auth).json()
    assert project["status"] == "ready" and project["source_metadata"]["has_audio"] is False
    cid = client.post(
        f"/api/v1/projects/{pid}/clips",
        headers=auth,
        json={"title": "silent", "start_seconds": 0.5, "end_seconds": 3},
    ).json()["id"]
    client.post(f"/api/v1/clips/{cid}/render", headers=auth)
    url = client.get(f"/api/v1/clips/{cid}/download", headers=auth).json()["url"]
    out = tmp_path / "silent.mp4"
    out.write_bytes(_download(client, url))
    assert probe(out).has_audio is False


def test_clip_validation(client: TestClient, auth: dict[str, str], sample_video: Path) -> None:
    pid = upload_video(client, auth, sample_video)["project"]["id"]
    cases = [
        {"title": "past end", "start_seconds": 5, "end_seconds": 60},
        {"title": "reversed", "start_seconds": 5, "end_seconds": 4},
        {"title": "too short", "start_seconds": 5, "end_seconds": 5.5},
        {
            "title": "bad ratio",
            "start_seconds": 0,
            "end_seconds": 3,
            "render_settings": {"aspect_ratio": "4:5"},
        },
        {
            "title": "bad crop",
            "start_seconds": 0,
            "end_seconds": 3,
            "render_settings": {"crop_x": 2},
        },
        {
            "title": "extra key",
            "start_seconds": 0,
            "end_seconds": 3,
            "render_settings": {"vf": "evil"},
        },
    ]
    for body in cases:
        resp = client.post(f"/api/v1/projects/{pid}/clips", headers=auth, json=body)
        assert resp.status_code == 422, (body, resp.text)


def test_clips_require_processed_source(client: TestClient, auth: dict[str, str]) -> None:
    pid = client.post("/api/v1/projects", json={"title": "Empty"}, headers=auth).json()["id"]
    resp = client.post(
        f"/api/v1/projects/{pid}/clips",
        headers=auth,
        json={"title": "x", "start_seconds": 0, "end_seconds": 2},
    )
    assert resp.status_code == 409


def test_cross_user_clip_and_media_access(
    client: TestClient, auth: dict[str, str], sample_video: Path
) -> None:
    pid = upload_video(client, auth, sample_video)["project"]["id"]
    cid = client.post(
        f"/api/v1/projects/{pid}/clips",
        headers=auth,
        json={"title": "mine", "start_seconds": 0, "end_seconds": 2},
    ).json()["id"]
    job = client.post(f"/api/v1/clips/{cid}/render", headers=auth).json()
    media = client.get(f"/api/v1/projects/{pid}/media", headers=auth).json()
    rendered = next(m for m in media if m["asset_type"] == "rendered_clip")

    intruder = register(client)
    for method, path in [
        ("get", f"/api/v1/clips/{cid}"),
        ("patch", f"/api/v1/clips/{cid}"),
        ("delete", f"/api/v1/clips/{cid}"),
        ("post", f"/api/v1/clips/{cid}/render"),
        ("post", f"/api/v1/clips/{cid}/duplicate"),
        ("get", f"/api/v1/clips/{cid}/download"),
        ("get", f"/api/v1/jobs/{job['id']}"),
        ("post", f"/api/v1/jobs/{job['id']}/retry"),
        ("get", f"/api/v1/exports/{rendered['id']}"),
        ("delete", f"/api/v1/media/{rendered['id']}"),
        ("get", f"/api/v1/projects/{pid}/source-url"),
    ]:
        resp = client.request(method, path, json={"title": "x"}, headers=intruder)
        assert resp.status_code == 404, (method, path, resp.status_code)
    assert client.get("/api/v1/exports", headers=intruder).json()["total"] == 0


def test_duplicate_and_delete_clip(
    client: TestClient, auth: dict[str, str], sample_video: Path
) -> None:
    pid = upload_video(client, auth, sample_video)["project"]["id"]
    cid = client.post(
        f"/api/v1/projects/{pid}/clips",
        headers=auth,
        json={
            "title": "orig",
            "start_seconds": 1,
            "end_seconds": 3,
            "render_settings": {"aspect_ratio": "1:1"},
        },
    ).json()["id"]
    client.post(f"/api/v1/clips/{cid}/render", headers=auth)
    dup = client.post(f"/api/v1/clips/{cid}/duplicate", headers=auth).json()
    assert dup["title"] == "orig (copy)" and dup["status"] == "draft"
    assert dup["render_settings"]["aspect_ratio"] == "1:1"

    from app.services.storage import get_storage

    storage = get_storage()
    media = client.get(f"/api/v1/projects/{pid}/media", headers=auth).json()
    key_count_before = len(media)
    assert client.delete(f"/api/v1/clips/{cid}", headers=auth).status_code == 204
    media_after = client.get(f"/api/v1/projects/{pid}/media", headers=auth).json()
    assert len(media_after) == key_count_before - 2  # rendered mp4 + thumbnail removed
    assert storage.check()


def test_delete_project_removes_files(
    client: TestClient, auth: dict[str, str], sample_video: Path
) -> None:
    from app.services.storage import get_storage

    pid = upload_video(client, auth, sample_video)["project"]["id"]
    storage = get_storage()
    root = storage.root  # type: ignore[attr-defined]
    assert any(root.rglob(f"*{pid}*"))
    assert client.delete(f"/api/v1/projects/{pid}", headers=auth).status_code == 204
    assert not any(p for p in root.rglob("*") if pid in str(p))
