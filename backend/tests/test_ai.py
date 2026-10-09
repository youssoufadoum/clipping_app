"""AI shorts: captions, candidate validation, the Gemini client (mocked HTTP) and the
full upload -> transcribe -> pick -> render pipeline with a fake provider.

No real AI API is called in tests.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.errors import ProcessingError
from app.services.ai.clip_selection import clean_segments, validate_candidates
from app.services.ai.gemini import GeminiProvider
from app.services.ai.types import AnalysisRequest, TranscriptSegment
from app.services.captions import build_cues, to_ass, to_srt, to_vtt
from tests.conftest import register

# --- captions ---------------------------------------------------------------


def test_cues_are_chunked_and_relative_to_clip() -> None:
    segs = [
        {"start": 10.0, "end": 14.0, "text": "This is a longer sentence that needs splitting"},
        {"start": 30.0, "end": 32.0, "text": "outside the clip"},
    ]
    cues = build_cues(segs, clip_start=9.0, clip_end=20.0)
    assert len(cues) >= 2
    assert cues[0].start == pytest.approx(1.0)
    assert cues[-1].end == pytest.approx(5.0, abs=0.05)
    assert all(len(c.text.split()) <= 4 for c in cues)
    assert all(c.end <= 11.0 for c in cues)
    assert " ".join(c.text for c in cues) == segs[0]["text"]


def test_cues_clamped_to_clip_bounds() -> None:
    cues = build_cues(
        [{"start": 0, "end": 10, "text": "one two three four five six seven eight"}],
        clip_start=5,
        clip_end=8,
    )
    assert cues and cues[0].start >= 0 and cues[-1].end <= 3


def test_ass_escapes_override_syntax() -> None:
    cues = build_cues([{"start": 0, "end": 2, "text": r"{\pos(1,1)} hi\N"}], 0, 2)
    ass = to_ass(cues, 1080, 1920)
    events = [line for line in ass.splitlines() if line.startswith("Dialogue")]
    assert events and all("{" not in e and "\\" not in e for e in events)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass


def test_srt_and_vtt_format() -> None:
    cues = build_cues([{"start": 0, "end": 3.5, "text": "Hello there world"}], 0, 10)
    srt = to_srt(cues)
    assert srt.startswith("1\n00:00:00,000 --> ")
    vtt = to_vtt(cues)
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> ")


# --- candidate validation -----------------------------------------------------


def _segments(n: int, step: float = 4.0) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(i * step, i * step + step - 0.2, f"Sentence number {i}.")
        for i in range(n)
    ]


def test_validate_candidates_fits_ranks_and_dedupes() -> None:
    segs = _segments(40)  # 160 s of speech
    req = AnalysisRequest(target_seconds=30, count=3)
    raw = [
        {
            "start_segment": 0,
            "end_segment": 1,
            "title": "Short one",
            "selection_reason": "r",
            "estimated_engagement_score": 70,
        },  # too short: extended to >= 20 s
        {
            "start_segment": 1,
            "end_segment": 7,
            "title": "Overlap",
            "selection_reason": "r",
            "estimated_engagement_score": 60,
        },  # overlaps the first -> dropped
        {
            "start_segment": 20,
            "end_segment": 39,
            "title": "Too long",
            "selection_reason": "r",
            "estimated_engagement_score": 90,
        },  # trimmed to <= 40 s
        {"start_segment": 999, "end_segment": 1000, "title": "Invalid"},  # bad indices
        {"start_segment": "x", "end_segment": 2},  # malformed
    ]
    out = validate_candidates(raw, segs, media_duration=160, request=req)
    assert [c.title for c in out] == ["Too long", "Short one"]
    for c in out:
        assert req.min_seconds <= c.duration_seconds <= req.max_seconds
        assert 0 <= c.start_time_seconds < c.end_time_seconds <= 160
        # Starts and ends on real segment boundaries
        assert any(abs(s.start - c.start_time_seconds) < 0.01 for s in segs)
        assert any(abs(s.end - c.end_time_seconds) < 0.01 for s in segs)
    assert out[0].estimated_engagement_score == 90


def test_validate_candidates_clamps_scores_and_text() -> None:
    segs = _segments(20)
    out = validate_candidates(
        [
            {
                "start_segment": 0,
                "end_segment": 7,
                "title": "T" * 500,
                "selection_reason": "ok",
                "estimated_engagement_score": 1e9,
                "confidence": -3,
            }
        ],
        segs,
        80,
        AnalysisRequest(target_seconds=30),
    )
    assert out[0].estimated_engagement_score == 100 and out[0].confidence == 0
    assert len(out[0].title) <= 120


def test_clean_segments_rejects_garbage() -> None:
    segs = clean_segments(
        [
            {"start": 1, "end": 3, "text": " hello   world "},
            {"start": 5, "end": 4, "text": "reversed"},
            {"start": "a", "end": 4, "text": "bad"},
            {"start": 2.5, "end": 6, "text": "overlaps previous"},
            {"start": 999, "end": 1000, "text": "past the chunk"},
            {"start": 7, "end": 8, "text": ""},
        ],
        offset=100,
        chunk_seconds=60,
    )
    assert [s.text for s in segs] == ["hello world", "overlaps previous"]
    assert segs[0].start == 101 and segs[0].end <= segs[1].start


# --- Gemini client (mocked HTTP) -------------------------------------------


def _gemini(handler) -> GeminiProvider:
    return GeminiProvider("test-key", "gemini-test", transport=httpx.MockTransport(handler))


def _ok(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
    )


def test_gemini_transcribe_sends_audio_and_parses(tmp_path: Path) -> None:
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"ID3fakeaudio")
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return _ok({"language": "en", "segments": [{"start": 0.5, "end": 2.0, "text": "Hi."}]})

    lang, segs = _gemini(handler).transcribe_chunk(audio, 10, None)
    assert lang == "en" and segs[0].text == "Hi."
    assert seen["key"] == "test-key" and "key=" not in seen["url"]  # key never in the URL
    assert ":generateContent" in seen["url"]
    parts = seen["body"]["contents"][0]["parts"]
    assert parts[0]["inline_data"]["mime_type"] == "audio/mp3"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_bad_key_is_not_retried(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            400,
            json={
                "error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}
            },
        )

    with pytest.raises(ProcessingError) as e:
        _gemini(handler).propose_clips(_segments(5), AnalysisRequest(30))
    assert e.value.code == "AI_AUTH_FAILED" and not e.value.retryable and len(calls) == 1


def test_gemini_retries_rate_limits_and_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.ai.gemini.time.sleep", lambda _s: None)
    responses = iter(
        [
            httpx.Response(429, json={}),
            httpx.Response(
                200, json={"candidates": [{"content": {"parts": [{"text": "{not json"}]}}]}
            ),
            _ok(
                {
                    "clips": [
                        {
                            "start_segment": 0,
                            "end_segment": 2,
                            "title": "t",
                            "selection_reason": "r",
                            "estimated_engagement_score": 50,
                        }
                    ]
                }
            ),
        ]
    )
    clips = _gemini(lambda _r: next(responses)).propose_clips(_segments(5), AnalysisRequest(30))
    assert clips[0]["title"] == "t"


def test_gemini_gives_up_with_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.ai.gemini.time.sleep", lambda _s: None)
    with pytest.raises(ProcessingError) as e:
        _gemini(lambda _r: httpx.Response(503, json={})).propose_clips(
            _segments(3), AnalysisRequest(30)
        )
    assert e.value.retryable and e.value.code == "AI_UNAVAILABLE"
    blocked = _gemini(
        lambda _r: httpx.Response(200, json={"candidates": [{"finishReason": "SAFETY"}]})
    )
    with pytest.raises(ProcessingError) as e:
        blocked.propose_clips(_segments(3), AnalysisRequest(30))
    assert e.value.code == "AI_BLOCKED"


# --- end-to-end pipeline with a fake provider --------------------------------


class FakeProvider:
    """Deterministic stand-in for Gemini used only in tests."""

    name = "fake"

    def __init__(self, speech: bool = True) -> None:
        self.speech = speech
        self.transcribe_calls: list[float] = []

    def transcribe_chunk(self, audio: Path, chunk_seconds: float, language: str | None):
        assert audio.stat().st_size > 0  # real audio was extracted by FFmpeg
        self.transcribe_calls.append(chunk_seconds)
        if not self.speech:
            return None, []
        segs = [
            TranscriptSegment(t, min(t + 3.8, chunk_seconds), f"Point {int(t)} is key.")
            for t in range(0, int(chunk_seconds) - 1, 4)
        ]
        return "en", segs

    def propose_clips(self, segments, request):
        n = len(segments)
        return [
            {
                "start_segment": 0,
                "end_segment": min(6, n - 1),
                "title": "Hook moment",
                "selection_reason": "Strong opening claim.",
                "estimated_engagement_score": 82,
            },
            {
                "start_segment": 1,
                "end_segment": min(7, n - 1),
                "title": "Duplicate",
                "selection_reason": "overlaps",
                "estimated_engagement_score": 40,
            },
        ]


@pytest.fixture(scope="session")
def talk_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("ai") / "talk.mp4"
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
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def fake_ai(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    from app.core.config import get_settings

    provider = FakeProvider()
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "transcription_chunk_seconds", 25)
    monkeypatch.setattr("app.services.ai.get_ai_provider", lambda: provider)
    return provider


def _upload(
    client: TestClient, headers: dict[str, str], video: Path, auto_shorts: dict | None
) -> str:
    pid = client.post("/api/v1/projects", json={"title": "Talk"}, headers=headers).json()["id"]
    data = video.read_bytes()
    target = client.post(
        f"/api/v1/projects/{pid}/uploads/initiate",
        headers=headers,
        json={"filename": video.name, "content_type": "video/mp4", "size_bytes": len(data)},
    ).json()
    client.put(
        target["url"].replace("http://testserver", ""), content=data, headers=target["headers"]
    )
    body: dict[str, Any] = {"upload_id": target["upload_id"]}
    if auto_shorts is not None:
        body["auto_shorts"] = auto_shorts
    resp = client.post(f"/api/v1/projects/{pid}/uploads/complete", headers=headers, json=body)
    assert resp.status_code == 200, resp.text
    return pid


def test_upload_with_auto_shorts_creates_rendered_captioned_clips(
    client: TestClient,
    auth: dict[str, str],
    talk_video: Path,
    fake_ai: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.worker import tasks

    commands: list[list[str]] = []
    real_run = tasks.run_ffmpeg

    def spy(cmd, **kw):
        commands.append(cmd)
        return real_run(cmd, **kw)

    monkeypatch.setattr(tasks, "run_ffmpeg", spy)
    pid = _upload(client, auth, talk_video, {"target_seconds": 30, "count": 3})

    project = client.get(f"/api/v1/projects/{pid}", headers=auth).json()
    assert project["status"] == "ready"
    assert fake_ai.transcribe_calls == [25, 15]  # chunked: 0-25 s and 25-40 s

    transcript = client.get(f"/api/v1/projects/{pid}/transcript", headers=auth).json()
    assert transcript["provider"] == "fake" and transcript["has_word_timestamps"] is False
    assert transcript["segments"][0]["text"] == "Point 0 is key."
    assert any(s["start"] >= 25 for s in transcript["segments"])  # offset applied to chunk 2

    clips = client.get(f"/api/v1/projects/{pid}/clips", headers=auth).json()
    assert [c["title"] for c in clips] == ["Hook moment"]  # duplicate dropped
    clip = clips[0]
    assert clip["origin"] == "ai" and clip["engagement_score"] == 82
    assert 20 <= clip["duration_seconds"] <= 40
    assert clip["selection_reason"] == "Strong opening claim."
    assert clip["render_settings"]["captions"] is True
    assert clip["status"] == "rendered"

    render_vf = [c[c.index("-vf") + 1] for c in commands if "-vf" in c and "libx264" in c]
    assert render_vf and "subtitles=" in render_vf[-1]

    url = client.get(f"/api/v1/clips/{clip['id']}/download", headers=auth).json()["url"]
    out = tmp_path / "short.mp4"
    out.write_bytes(client.get(url.replace("http://testserver", "")).content)
    from app.services.media.probe import probe

    info = probe(out)
    assert info.height > info.width and abs(info.duration - clip["duration_seconds"]) < 0.3

    usage = client.get("/api/v1/usage", headers=auth).json()
    assert usage["ai_minutes_used"] == pytest.approx(0.7)  # 40 s -> 0.7 min
    srt = client.get(f"/api/v1/clips/{clip['id']}/subtitles?format=srt", headers=auth)
    assert srt.status_code == 200 and "Point 0 is key." in srt.text
    assert "attachment" in srt.headers["content-disposition"]


def test_analyze_reuses_transcript_and_respects_quota(
    client: TestClient,
    auth: dict[str, str],
    talk_video: Path,
    fake_ai: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid = _upload(client, auth, talk_video, None)
    assert client.get(f"/api/v1/projects/{pid}/clips", headers=auth).json() == []
    job = client.post(
        f"/api/v1/projects/{pid}/analyze",
        headers=auth,
        json={"target_seconds": 60, "count": 1, "auto_render": False},
    )
    assert job.status_code == 200, job.text
    state = client.get(f"/api/v1/jobs/{job.json()['id']}", headers=auth).json()
    assert state["status"] == "succeeded"
    clips = client.get(f"/api/v1/projects/{pid}/clips", headers=auth).json()
    assert len(clips) == 1 and clips[0]["status"] == "draft"  # not auto-rendered

    # Second run reuses the transcript: no new transcription and no extra AI minutes.
    calls_before = len(fake_ai.transcribe_calls)
    client.post(f"/api/v1/projects/{pid}/analyze", headers=auth, json={"auto_render": False})
    assert len(fake_ai.transcribe_calls) == calls_before
    assert client.get("/api/v1/usage", headers=auth).json()["ai_minutes_used"] == pytest.approx(0.7)

    # Quota: a fresh project with no transcript is refused when AI minutes run out.
    from dataclasses import replace

    from app.core import plans

    monkeypatch.setitem(plans.PLANS, "free", replace(plans.PLANS["free"], monthly_ai_minutes=0))
    pid2 = _upload(client, auth, talk_video, None)
    resp = client.post(f"/api/v1/projects/{pid2}/analyze", headers=auth, json={})
    assert resp.status_code == 402 and resp.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_no_speech_fails_safely_and_keeps_project_usable(
    client: TestClient,
    auth: dict[str, str],
    talk_video: Path,
    fake_ai: FakeProvider,
) -> None:
    fake_ai.speech = False
    pid = _upload(client, auth, talk_video, None)
    job = client.post(f"/api/v1/projects/{pid}/analyze", headers=auth, json={}).json()
    state = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert state["status"] == "failed" and state["error_code"] == "NO_SPEECH"
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["status"] == "ready"
    # Manual clips still work
    resp = client.post(
        f"/api/v1/projects/{pid}/clips",
        headers=auth,
        json={"title": "manual", "start_seconds": 0, "end_seconds": 5},
    )
    assert resp.status_code == 201


def test_provider_failure_returns_project_to_ready(
    client: TestClient,
    auth: dict[str, str],
    talk_video: Path,
    fake_ai: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_a, **_k):
        raise ProcessingError("AI_AUTH_FAILED", "The AI service rejected this server's API key.")

    monkeypatch.setattr(fake_ai, "transcribe_chunk", broken)
    pid = _upload(client, auth, talk_video, None)
    job = client.post(f"/api/v1/projects/{pid}/analyze", headers=auth, json={}).json()
    state = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert state["status"] == "failed" and state["error_code"] == "AI_AUTH_FAILED"
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["status"] == "ready"
    assert client.get("/api/v1/usage", headers=auth).json()["ai_minutes_used"] == 0


def test_transcript_edit_updates_captions_and_is_private(
    client: TestClient,
    auth: dict[str, str],
    talk_video: Path,
    fake_ai: FakeProvider,
) -> None:
    pid = _upload(client, auth, talk_video, {"target_seconds": 30, "auto_render": False})
    resp = client.patch(
        f"/api/v1/projects/{pid}/transcript",
        headers=auth,
        json={"segments": [{"index": 0, "text": "  Corrected   opening line. "}]},
    )
    assert resp.status_code == 200
    assert resp.json()["segments"][0]["text"] == "Corrected opening line."
    clip_id = client.get(f"/api/v1/projects/{pid}/clips", headers=auth).json()[0]["id"]
    vtt = client.get(f"/api/v1/clips/{clip_id}/subtitles?format=vtt", headers=auth).text
    assert vtt.startswith("WEBVTT") and "Corrected opening" in vtt
    bad = client.patch(
        f"/api/v1/projects/{pid}/transcript",
        headers=auth,
        json={"segments": [{"index": 9999, "text": "x"}]},
    )
    assert bad.status_code == 422

    intruder = register(client)
    assert client.get(f"/api/v1/projects/{pid}/transcript", headers=intruder).status_code == 404
    assert (
        client.patch(
            f"/api/v1/projects/{pid}/transcript",
            headers=intruder,
            json={"segments": [{"index": 0, "text": "x"}]},
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/clips/{clip_id}/subtitles", headers=intruder).status_code == 404
    assert (
        client.post(f"/api/v1/projects/{pid}/analyze", headers=intruder, json={}).status_code == 404
    )


def test_analyze_validation(
    client: TestClient, auth: dict[str, str], fake_ai: FakeProvider
) -> None:
    pid = client.post("/api/v1/projects", json={"title": "x"}, headers=auth).json()["id"]
    assert (
        client.post(
            f"/api/v1/projects/{pid}/analyze", headers=auth, json={"target_seconds": 45}
        ).status_code
        == 422
    )
    assert (
        client.post(f"/api/v1/projects/{pid}/analyze", headers=auth, json={"count": 50}).status_code
        == 422
    )
    resp = client.post(f"/api/v1/projects/{pid}/analyze", headers=auth, json={})
    assert resp.status_code == 409  # no processed video yet
    assert client.get("/api/v1/system/status").json()["ai_available"] is True


def test_unverified_supabase_email_rejected() -> None:
    import time

    import jwt

    from app.core.config import Settings
    from app.core.errors import Unauthorized
    from app.core.security import verify_access_token

    settings = Settings(
        auth_mode="supabase", supabase_url="https://p.supabase.co", supabase_jwt_secret="s" * 40
    )
    claims = {
        "sub": str(uuid.uuid4()),
        "email": "a@b.io",
        "aud": "authenticated",
        "iss": "https://p.supabase.co/auth/v1",
        "exp": int(time.time()) + 60,
        "user_metadata": {"email_verified": False},
    }
    with pytest.raises(Unauthorized) as e:
        verify_access_token(jwt.encode(claims, "s" * 40, algorithm="HS256"), settings)
    assert e.value.code == "EMAIL_NOT_VERIFIED"
    claims["user_metadata"]["email_verified"] = True
    assert verify_access_token(jwt.encode(claims, "s" * 40, algorithm="HS256"), settings).email


def test_project_reports_has_transcript(
    client: TestClient,
    auth: dict[str, str],
    talk_video: Path,
    fake_ai: FakeProvider,
) -> None:
    pid = _upload(client, auth, talk_video, None)
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["has_transcript"] is False
    client.post(f"/api/v1/projects/{pid}/analyze", headers=auth, json={"auto_render": False})
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["has_transcript"] is True
