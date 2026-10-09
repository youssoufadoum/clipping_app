"""YouTube link import via yt-dlp.

Only links to a single YouTube video are accepted. The URL the user pastes is
never fetched directly: we extract and validate the 11-character video id and
rebuild a canonical youtube.com URL, so arbitrary hosts (SSRF) are impossible.

Downloading from YouTube is restricted by YouTube's Terms of Service. Users
must confirm they own the video or have permission, operators can switch the
feature off with YOUTUBE_IMPORT_ENABLED=false, and YouTube may refuse
downloads from some servers; those cases surface as clear, safe errors.
"""

from __future__ import annotations

import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.core.errors import ProcessingError

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
PATH_PREFIXES = ("shorts", "live", "embed", "v", "e")


def parse_youtube_url(raw: str) -> str | None:
    """Return the video id for a single-video YouTube link, or None."""
    text = (raw or "").strip()
    if not text or len(text) > 2048 or any(c.isspace() for c in text):
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    if host not in ALLOWED_HOSTS or port not in (None, 80, 443):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    candidate: str | None = None
    if host.endswith("youtu.be"):
        candidate = parts[0] if parts else None
    elif parts[:1] == ["watch"]:
        values = parse_qs(parsed.query).get("v") or []
        candidate = values[0] if values else None
    elif len(parts) >= 2 and parts[0] in PATH_PREFIXES:
        candidate = parts[1]
    if candidate and VIDEO_ID.match(candidate):
        return candidate
    return None


def canonical_url(video_id: str) -> str:
    assert VIDEO_ID.match(video_id)
    return f"https://www.youtube.com/watch?v={video_id}"


@dataclass
class VideoInfo:
    video_id: str
    title: str
    duration: float | None
    is_live: bool
    uploader: str | None
    thumbnail: str | None


def _deno_path() -> str | None:
    found = shutil.which("deno")
    if found:
        return found
    candidate = Path(sys.executable).parent / "deno"
    return str(candidate) if candidate.exists() else None


def _base_options() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "cachedir": False,
        "noprogress": True,
        "extractor_retries": 2,
    }
    deno = _deno_path()
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    return opts


_ERROR_MAP: list[tuple[re.Pattern[str], str, str, bool]] = [
    (
        re.compile(r"not a bot|confirm you.re not", re.I),
        "YOUTUBE_BLOCKED",
        "YouTube refused the download from this server. Try again later, or download the "
        "video yourself and upload the file.",
        False,
    ),
    (
        re.compile(r"private video", re.I),
        "VIDEO_PRIVATE",
        "This video is private. Make it public or unlisted, or upload the file instead.",
        False,
    ),
    (
        re.compile(r"confirm your age|age.restricted|inappropriate", re.I),
        "AGE_RESTRICTED",
        "This video is age-restricted and can't be imported. Upload the file instead.",
        False,
    ),
    (
        re.compile(r"members.only|join this channel", re.I),
        "MEMBERS_ONLY",
        "This video is for channel members only. Upload the file instead.",
        False,
    ),
    (
        re.compile(r"premiere|will begin|is upcoming|live event", re.I),
        "NOT_AVAILABLE_YET",
        "This video hasn't been released yet.",
        False,
    ),
    (
        re.compile(r"copyright|removed|terminated|unavailable|does not exist", re.I),
        "VIDEO_UNAVAILABLE",
        "This video is unavailable on YouTube.",
        False,
    ),
    (
        re.compile(r"429|too many requests", re.I),
        "YOUTUBE_RATE_LIMITED",
        "YouTube is limiting requests right now. We'll retry automatically.",
        True,
    ),
    (
        re.compile(r"timed out|connection|network|temporar|reset by peer|name resolution", re.I),
        "NETWORK_ERROR",
        "We couldn't reach YouTube. We'll retry automatically.",
        True,
    ),
]


def map_download_error(message: str) -> ProcessingError:
    for pattern, code, safe, retryable in _ERROR_MAP:
        if pattern.search(message):
            return ProcessingError(code, safe, retryable=retryable)
    return ProcessingError(
        "DOWNLOAD_FAILED", "The video could not be downloaded from YouTube.", retryable=True
    )


class YouTubeImporter:
    """Thin wrapper around yt-dlp so tests can substitute a fake."""

    name = "youtube"

    def fetch_info(self, video_id: str) -> VideoInfo:
        import yt_dlp

        try:
            with yt_dlp.YoutubeDL({**_base_options(), "skip_download": True}) as ydl:
                info = ydl.extract_info(canonical_url(video_id), download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise map_download_error(str(exc)) from None
        if not isinstance(info, dict):
            raise ProcessingError(
                "DOWNLOAD_FAILED", "YouTube returned no video information.", retryable=True
            )
        return VideoInfo(
            video_id=video_id,
            title=str(info.get("title") or "YouTube video")[:200],
            duration=float(info["duration"]) if info.get("duration") else None,
            is_live=bool(
                info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming")
            ),
            uploader=(str(info["uploader"])[:200] if info.get("uploader") else None),
            thumbnail=info.get("thumbnail"),
        )

    def download(
        self,
        video_id: str,
        dest_dir: Path,
        max_bytes: int,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> Path:
        import yt_dlp

        def hook(d: dict[str, Any]) -> None:
            if should_cancel and should_cancel():
                raise yt_dlp.utils.DownloadCancelled("cancelled")
            if d.get("status") == "downloading" and on_progress:
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total:
                    on_progress(min(float(d.get("downloaded_bytes") or 0) / float(total), 1.0))

        opts = {
            **_base_options(),
            # Prefer H.264 + AAC so every browser can preview the source; cap at 1080p.
            "format": (
                "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b"
            ),
            "merge_output_format": "mp4",
            "outtmpl": str(dest_dir / "source.%(ext)s"),
            "max_filesize": max_bytes,
            "progress_hooks": [hook],
            "overwrites": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([canonical_url(video_id)])
        except yt_dlp.utils.DownloadCancelled:
            raise ProcessingError("CANCELLED", "The job was cancelled.") from None
        except yt_dlp.utils.DownloadError as exc:
            raise map_download_error(str(exc)) from None
        files = [p for p in dest_dir.glob("source.*") if p.suffix not in (".part", ".ytdl")]
        if not files:
            raise ProcessingError(
                "FILE_TOO_LARGE", "The video is larger than your plan's upload limit."
            )
        return max(files, key=lambda p: p.stat().st_size)


def get_importer() -> YouTubeImporter:
    return YouTubeImporter()
