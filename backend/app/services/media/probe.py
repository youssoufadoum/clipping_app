"""Media inspection with ffprobe and content sniffing."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.errors import ProcessingError

ALLOWED_CONTAINERS = {
    "video/mp4": {".mp4", ".m4v"},
    "video/quicktime": {".mov"},
    "video/webm": {".webm"},
}
ALLOWED_EXTENSIONS = {ext for exts in ALLOWED_CONTAINERS.values() for ext in exts}
ALLOWED_MIME_TYPES = set(ALLOWED_CONTAINERS)


def sniff_container(head: bytes) -> str | None:
    """Identify a container from its first bytes. Returns a MIME type or None."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        return "video/quicktime" if brand == b"qt  " else "video/mp4"
    if len(head) >= 8 and head[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip"):
        return "video/quicktime"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    return None


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool
    format_name: str | None
    bit_rate: int | None
    rotation: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "has_audio": self.has_audio,
            "format_name": self.format_name,
            "bit_rate": self.bit_rate,
            "rotation": self.rotation,
        }


def _parse_rate(rate: str | None) -> float | None:
    if not rate or rate in ("0/0", "0"):
        return None
    try:
        if "/" in rate:
            num, den = rate.split("/")
            return round(float(num) / float(den), 3) if float(den) else None
        return float(rate)
    except ValueError:
        return None


def _rotation(stream: dict[str, Any]) -> int:
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            try:
                return int(float(side["rotation"])) % 360
            except (TypeError, ValueError):
                pass
    tag = (stream.get("tags") or {}).get("rotate")
    try:
        return int(tag) % 360 if tag is not None else 0
    except ValueError:
        return 0


def parse_probe_output(data: dict[str, Any]) -> MediaInfo:
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")
        ),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ProcessingError("NO_VIDEO_STREAM", "The file does not contain a video stream.")

    duration_raw = fmt.get("duration") or video.get("duration")
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        raise ProcessingError("INVALID_DURATION", "Could not determine the video's duration.")

    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ProcessingError("INVALID_DIMENSIONS", "Could not determine the video's dimensions.")

    rotation = _rotation(video)
    if rotation in (90, 270):
        width, height = height, width  # ffmpeg auto-rotates, so report display dimensions

    bit_rate = fmt.get("bit_rate")
    return MediaInfo(
        duration=round(duration, 3),
        width=width,
        height=height,
        fps=_parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate")),
        video_codec=video.get("codec_name"),
        audio_codec=audio.get("codec_name") if audio else None,
        has_audio=audio is not None,
        format_name=fmt.get("format_name"),
        bit_rate=int(bit_rate) if bit_rate and str(bit_rate).isdigit() else None,
        rotation=rotation,
        raw={"format_name": fmt.get("format_name"), "nb_streams": len(streams)},
    )


def probe(path: Path | str, timeout: int = 120) -> MediaInfo:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ProcessingError(
            "PROBE_TIMEOUT", "Inspecting the video took too long.", retryable=True
        ) from exc
    if result.returncode != 0:
        raise ProcessingError(
            "UNREADABLE_MEDIA", "The file could not be read as a video. It may be corrupted."
        )
    try:
        data = json.loads(result.stdout or b"{}")
    except json.JSONDecodeError as exc:
        raise ProcessingError("UNREADABLE_MEDIA", "The file could not be read as a video.") from exc
    return parse_probe_output(data)
