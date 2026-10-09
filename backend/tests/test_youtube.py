"""YouTube link import. yt-dlp is replaced by fakes; no network access to YouTube."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ProcessingError
from app.services.importers import youtube
from app.services.importers.youtube import VideoInfo, map_download_error, parse_youtube_url
from tests.conftest import register

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}&t=42s&list=PL1",
        f"http://m.youtube.com/watch?feature=share&v={VID}",
        f"https://music.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}",
        f"youtu.be/{VID}?si=abc",
        f"www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/live/{VID}?feature=share",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube-nocookie.com/embed/{VID}",
        f"  https://www.youtube.com/watch?v={VID}  ",
    ],
)
def test_accepts_single_video_links(url: str) -> None:
    assert parse_youtube_url(url) == VID


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        f"https://evil.com/watch?v={VID}",
        f"https://youtube.com.evil.com/watch?v={VID}",
        f"https://evil.com/?u=https://youtube.com/watch?v={VID}",
        f"https://user:pass@youtube.com/watch?v={VID}",
        f"https://youtube.com:8080/watch?v={VID}",
        f"ftp://youtube.com/watch?v={VID}",
        "https://www.youtube.com/playlist?list=PL0123456789",
        "https://www.youtube.com/@somechannel",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ%27;--",
        "https://youtu.be/",
        "http://127.0.0.1/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=" + "a" * 3000,
    ],
)
def test_rejects_everything_else(url: str) -> None:
    assert parse_youtube_url(url) is None


def test_canonical_url_is_rebuilt_from_id() -> None:
    assert youtube.canonical_url(VID) == f"https://www.youtube.com/watch?v={VID}"


@pytest.mark.parametrize(
    ("message", "code", "retryable"),
    [
        ("ERROR: [youtube] x: Sign in to confirm you’re not a bot", "YOUTUBE_BLOCKED", False),
        ("ERROR: [youtube] x: Private video. Sign in", "VIDEO_PRIVATE", False),
        ("ERROR: Sign in to confirm your age", "AGE_RESTRICTED", False),
        ("ERROR: Join this channel to get access to members-only content", "MEMBERS_ONLY", False),
        ("ERROR: Video unavailable", "VIDEO_UNAVAILABLE", False),
        ("ERROR: HTTP Error 429: Too Many Requests", "YOUTUBE_RATE_LIMITED", True),
        ("ERROR: Read timed out", "NETWORK_ERROR", True),
        ("ERROR: something odd", "DOWNLOAD_FAILED", True),
    ],
)
def test_error_mapping(message: str, code: str, retryable: bool) -> None:
    err = map_download_error(message)
    assert err.code == code and err.retryable is retryable
    assert "ERROR" not in err.safe_message


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL."""

    last_opts: dict[str, Any] = {}
    info: dict[str, Any] = {"title": "My talk", "duration": 125.0, "uploader": "Ada"}
    error: str | None = None
    source: Path | None = None

    def __init__(self, opts: dict[str, Any]) -> None:
        FakeYDL.last_opts = opts

    def __enter__(self) -> FakeYDL:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        import yt_dlp

        assert url == f"https://www.youtube.com/watch?v={VID}"
        if FakeYDL.error:
            raise yt_dlp.utils.DownloadError(FakeYDL.error)
        return FakeYDL.info

    def download(self, urls: list[str]) -> None:
        dest = Path(self.last_opts["outtmpl"].replace("%(ext)s", "mp4"))
        for hook in self.last_opts["progress_hooks"]:
            hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
        if FakeYDL.source:
            shutil.copyfile(FakeYDL.source, dest)


@pytest.fixture
def fake_ydl(monkeypatch: pytest.MonkeyPatch) -> type[FakeYDL]:
    import yt_dlp

    FakeYDL.error, FakeYDL.source = None, None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def test_importer_fetch_info_and_options(fake_ydl: type[FakeYDL]) -> None:
    info = youtube.YouTubeImporter().fetch_info(VID)
    assert info.title == "My talk" and info.duration == 125.0 and not info.is_live
    opts = fake_ydl.last_opts
    assert opts["noplaylist"] is True and opts["cachedir"] is False
    assert "deno" in opts.get("js_runtimes", {})  # JS runtime needed for YouTube extraction
    fake_ydl.error = "ERROR: Private video"
    with pytest.raises(ProcessingError) as e:
        youtube.YouTubeImporter().fetch_info(VID)
    assert e.value.code == "VIDEO_PRIVATE"


def test_importer_download_reports_progress_and_limits(
    fake_ydl: type[FakeYDL], tmp_path: Path, sample_video: Path
) -> None:
    fake_ydl.source = sample_video
    seen: list[float] = []
    out = youtube.YouTubeImporter().download(VID, tmp_path, 10**9, on_progress=seen.append)
    assert out.exists() and seen == [0.5]
    opts = fake_ydl.last_opts
    assert opts["max_filesize"] == 10**9 and opts["merge_output_format"] == "mp4"
    assert "height<=1080" in opts["format"]
    # Nothing written (e.g. skipped because of max_filesize) -> clear error
    fake_ydl.source = None
    with pytest.raises(ProcessingError) as e:
        youtube.YouTubeImporter().download(VID, tmp_path / "empty", 10, None)
    assert e.value.code == "FILE_TOO_LARGE"


def test_importer_download_cancellation(fake_ydl: type[FakeYDL], tmp_path: Path) -> None:
    with pytest.raises(ProcessingError) as e:
        youtube.YouTubeImporter().download(VID, tmp_path, 10**9, should_cancel=lambda: True)
    assert e.value.code == "CANCELLED"


# --- API + pipeline ------------------------------------------------------------


class FakeImporter:
    name = "youtube"

    def __init__(self, video: Path) -> None:
        self.video = video
        self.info = VideoInfo(VID, "How to hook viewers", 40.0, False, "Ada", None)
        self.error: ProcessingError | None = None
        self.downloads = 0

    def fetch_info(self, video_id: str) -> VideoInfo:
        assert video_id == VID
        if self.error:
            raise self.error
        return self.info

    def download(self, video_id, dest_dir: Path, max_bytes, on_progress=None, should_cancel=None):
        self.downloads += 1
        if on_progress:
            on_progress(1.0)
        out = dest_dir / "source.mp4"
        shutil.copyfile(self.video, out)
        return out


@pytest.fixture
def importer(monkeypatch: pytest.MonkeyPatch, sample_video: Path) -> FakeImporter:
    fake = FakeImporter(sample_video)
    monkeypatch.setattr("app.services.importers.youtube.get_importer", lambda: fake)
    return fake


def _import(client: TestClient, headers: dict[str, str], **body: Any):
    payload = {"url": f"https://youtu.be/{VID}", "rights_confirmed": True, **body}
    return client.post("/api/v1/projects/import", headers=headers, json=payload)


def test_import_link_end_to_end(
    client: TestClient, auth: dict[str, str], importer: FakeImporter
) -> None:
    resp = _import(client, auth)
    assert resp.status_code == 201, resp.text
    pid = resp.json()["project"]["id"]
    project = client.get(f"/api/v1/projects/{pid}", headers=auth).json()
    assert project["status"] == "ready"
    assert project["title"] == "How to hook viewers"  # taken from YouTube
    assert project["source_type"] == "youtube"
    assert project["source_url"] == f"https://www.youtube.com/watch?v={VID}"
    assert project["source_width"] == 640 and project["thumbnail_url"]
    jobs = client.get(f"/api/v1/projects/{pid}/jobs", headers=auth).json()
    assert [j["job_type"] for j in jobs] == ["inspect_media", "import_url"]
    assert all(j["status"] == "succeeded" for j in jobs)
    usage = client.get("/api/v1/usage", headers=auth).json()
    assert usage["source_minutes_used"] == 0.2  # charged once at inspection, by real duration


def test_import_with_auto_shorts(
    client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path_factory
) -> None:
    import subprocess

    from tests.test_ai import FakeProvider

    video = tmp_path_factory.mktemp("yt") / "talk.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30:duration=40",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=300:duration=40",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(video),
        ],
        check=True,
    )
    fake = FakeImporter(video)
    monkeypatch.setattr("app.services.importers.youtube.get_importer", lambda: fake)
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.ai.get_ai_provider", lambda: FakeProvider())
    resp = _import(client, auth, auto_shorts={"target_seconds": 30, "count": 2})
    pid = resp.json()["project"]["id"]
    clips = client.get(f"/api/v1/projects/{pid}/clips", headers=auth).json()
    assert len(clips) == 1 and clips[0]["origin"] == "ai" and clips[0]["status"] == "rendered"


def test_import_requires_rights_and_valid_link(
    client: TestClient, auth: dict[str, str], importer: FakeImporter
) -> None:
    resp = _import(client, auth, rights_confirmed=False)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "RIGHTS_NOT_CONFIRMED"
    resp = _import(client, auth, url="https://vimeo.com/123456")
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "UNSUPPORTED_URL"
    resp = _import(client, auth, url="https://www.youtube.com/playlist?list=PL1")
    assert resp.status_code == 422
    assert importer.downloads == 0
    assert client.get("/api/v1/projects", headers=auth).json()["total"] == 0


def test_import_can_be_disabled(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    importer: FakeImporter,
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "youtube_import_enabled", False)
    resp = _import(client, auth)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "URL_IMPORT_DISABLED"
    assert client.get("/api/v1/system/status").json()["youtube_import"] is False


def test_too_long_video_rejected_before_download(
    client: TestClient, auth: dict[str, str], importer: FakeImporter
) -> None:
    importer.info = VideoInfo(VID, "Long stream", 5 * 3600.0, False, None, None)
    pid = _import(client, auth).json()["project"]["id"]
    project = client.get(f"/api/v1/projects/{pid}", headers=auth).json()
    assert project["status"] == "failed"
    assert project["latest_job"]["error_code"] == "VIDEO_TOO_LONG"
    assert importer.downloads == 0
    importer.info = VideoInfo(VID, "Live", None, True, None, None)
    pid = _import(client, auth).json()["project"]["id"]
    assert (
        client.get(f"/api/v1/projects/{pid}", headers=auth).json()["latest_job"]["error_code"]
        == "LIVE_NOT_SUPPORTED"
    )


def test_blocked_import_fails_safely_then_retries(
    client: TestClient, auth: dict[str, str], importer: FakeImporter
) -> None:
    importer.error = map_download_error("Sign in to confirm you're not a bot")
    pid = _import(client, auth).json()["project"]["id"]
    project = client.get(f"/api/v1/projects/{pid}", headers=auth).json()
    job = project["latest_job"]
    assert project["status"] == "failed" and job["error_code"] == "YOUTUBE_BLOCKED"
    assert "upload the file" in job["safe_error_message"]
    assert client.get("/api/v1/usage", headers=auth).json()["source_minutes_used"] == 0

    importer.error = None
    retry = client.post(f"/api/v1/jobs/{job['id']}/retry", headers=auth)
    assert retry.status_code == 200, retry.text
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["status"] == "ready"

    intruder = register(client)
    assert client.post(f"/api/v1/jobs/{job['id']}/retry", headers=intruder).status_code == 404


def test_transient_errors_are_retried_automatically(
    client: TestClient, auth: dict[str, str], importer: FakeImporter
) -> None:
    calls = {"n": 0}
    real = importer.fetch_info

    def flaky(video_id: str) -> VideoInfo:
        calls["n"] += 1
        if calls["n"] == 1:
            raise map_download_error("HTTP Error 429: Too Many Requests")
        return real(video_id)

    importer.fetch_info = flaky  # type: ignore[method-assign]
    pid = _import(client, auth).json()["project"]["id"]
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["status"] == "ready"
    jobs = client.get(f"/api/v1/projects/{pid}/jobs", headers=auth).json()
    assert next(j for j in jobs if j["job_type"] == "import_url")["attempt_count"] == 2


def test_cancel_queued_import(
    client: TestClient, auth: dict[str, str], importer: FakeImporter, defer_tasks: None
) -> None:
    body = _import(client, auth).json()
    cancelled = client.post(f"/api/v1/jobs/{body['job']['id']}/cancel", headers=auth).json()
    assert cancelled["status"] == "cancelled"
    pid = body["project"]["id"]
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["status"] == "cancelled"
    from app.worker.tasks import import_url_job

    import_url_job(uuid.UUID(body["job"]["id"]))  # late delivery is a no-op
    assert importer.downloads == 0


def test_rights_confirmation_is_audited(
    client: TestClient, auth: dict[str, str], importer: FakeImporter, db
) -> None:
    from sqlalchemy import select

    from app.models import AuditEvent

    pid = _import(client, auth).json()["project"]["id"]
    event = db.scalar(select(AuditEvent).where(AuditEvent.target_id == pid))
    assert event.action == "import.rights_confirmed"
    assert event.metadata_["url"].endswith(VID)
