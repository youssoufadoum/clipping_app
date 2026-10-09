"""Test configuration.

Tests run against a real PostgreSQL database (``TEST_DATABASE_URL``), real
FFmpeg/FFprobe and the local storage backend. Celery dispatch is replaced with
synchronous execution of the same task functions so the full job pipeline runs
inside the test process. External paid APIs are never called.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

_TMP = Path(os.environ.get("VIRELLO_TEST_TMP", "/tmp/virello-tests")) / uuid.uuid4().hex
os.environ.update(
    {
        "APP_ENV": "test",
        "AUTH_MODE": "local",
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_PATH": str(_TMP / "storage"),
        "WORK_DIR": str(_TMP / "work"),
        "BACKEND_PUBLIC_URL": "http://testserver",
        "API_SECRET_KEY": "test-secret-key-0123456789-abcdefghijklmnop",
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+psycopg://virello:virello@localhost:5432/virello_test",
        ),
        "REDIS_URL": "redis://localhost:6399/0",  # deliberately unused in tests
        "METRICS_TOKEN": "metrics-test-token",
        "ADMIN_EMAILS": "admin@example.com",
    }
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.ratelimit import get_rate_limiter  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean(_database: None) -> Iterator[None]:
    yield
    with get_engine().begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                    "AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    get_rate_limiter().reset()


@pytest.fixture(autouse=True)
def eager_queue(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    """Run dispatched tasks synchronously, through the real task functions."""
    from app.worker import tasks
    from app.worker.celery_app import celery_app

    sent: list[tuple[str, list[str]]] = []
    registry = {
        "virello.inspect_media": tasks.inspect_media,
        "virello.render_clip": tasks.render_clip,
        "virello.generate_shorts": tasks.generate_shorts,
        "virello.import_url": tasks.import_url,
    }

    def fake_send_task(name: str, args: list[str] | None = None, **_: object) -> None:
        sent.append((name, list(args or [])))
        if os.environ.get("VIRELLO_TEST_DEFER_TASKS") == "1":
            return
        registry[name](*(args or []))

    monkeypatch.setattr(celery_app, "send_task", fake_send_task)
    return sent


@pytest.fixture
def defer_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIRELLO_TEST_DEFER_TASKS", "1")


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with get_sessionmaker()() as session:
        yield session


def register(client: TestClient, email: str | None = None) -> dict[str, str]:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/local/register", json={"email": email, "password": "correct-horse-battery"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def auth(client: TestClient) -> dict[str, str]:
    return register(client)


@pytest.fixture
def other_auth(client: TestClient) -> dict[str, str]:
    return register(client)


def _make_video(path: Path, seconds: int, size: str, audio: bool = True) -> Path:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={size}:rate=30:duration={seconds}",
    ]
    if audio:
        cmd += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:a",
            "aac",
            "-shortest",
        ]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _make_video(tmp_path_factory.mktemp("media") / "sample.mp4", 12, "640x360")


@pytest.fixture(scope="session")
def silent_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _make_video(tmp_path_factory.mktemp("media") / "silent.mov", 4, "320x240", audio=False)


def upload_video(
    client: TestClient, headers: dict[str, str], video: Path, title: str = "Test project"
) -> dict:
    """Create a project and push a real file through the signed-upload flow."""
    project = client.post("/api/v1/projects", json={"title": title}, headers=headers).json()
    data = video.read_bytes()
    init = client.post(
        f"/api/v1/projects/{project['id']}/uploads/initiate",
        json={"filename": video.name, "content_type": "video/mp4", "size_bytes": len(data)},
        headers=headers,
    )
    assert init.status_code == 200, init.text
    target = init.json()
    put = client.put(
        target["url"].replace("http://testserver", ""), content=data, headers=target["headers"]
    )
    assert put.status_code == 200, put.text
    done = client.post(
        f"/api/v1/projects/{project['id']}/uploads/complete",
        json={"upload_id": target["upload_id"]},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    return done.json()
