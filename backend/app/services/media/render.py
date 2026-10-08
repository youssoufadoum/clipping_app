"""FFmpeg command construction and execution.

Commands are always built as argument lists and executed without a shell, so
user-controlled values (titles, timestamps) can never be interpreted as shell
syntax. Free text is never placed inside filter graphs; only validated numbers
and server-controlled strings are.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.errors import ProcessingError

log = logging.getLogger(__name__)

AspectRatio = Literal["9:16", "1:1", "16:9", "original"]
FitMode = Literal["crop", "pad"]

TARGET_SIZES: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}
WATERMARK_TEXT = "Made with Virello Studio"
WATERMARK_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


def _even(n: float) -> int:
    v = int(n)
    return max(2, v - (v % 2))


@dataclass(frozen=True)
class RenderSpec:
    start: float
    end: float
    source_width: int
    source_height: int
    aspect_ratio: AspectRatio = "9:16"
    fit: FitMode = "crop"
    crop_x: float = 0.5  # 0 = left edge, 1 = right edge
    crop_y: float = 0.5  # 0 = top edge, 1 = bottom edge
    pad_color: str = "black"
    watermark: bool = False
    normalize_audio: bool = False
    has_audio: bool = True

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


@dataclass(frozen=True)
class Geometry:
    crop_w: int
    crop_h: int
    crop_x: int
    crop_y: int
    out_w: int
    out_h: int


def compute_geometry(spec: RenderSpec) -> Geometry:
    sw, sh = spec.source_width, spec.source_height
    if spec.aspect_ratio == "original":
        tw, th = sw, sh
        scale = min(1.0, 1920 / max(sw, sh))
        return Geometry(_even(sw), _even(sh), 0, 0, _even(tw * scale), _even(th * scale))

    tw, th = TARGET_SIZES[spec.aspect_ratio]
    target_ar = tw / th
    if spec.fit == "pad":
        # Whole frame visible; output never upscales beyond the source's resolution.
        scale = min(1.0, max(sw / tw, sh / th))
        return Geometry(_even(sw), _even(sh), 0, 0, _even(tw * scale), _even(th * scale))

    if sw / sh > target_ar:
        crop_h = _even(sh)
        crop_w = _even(sh * target_ar)
    else:
        crop_w = _even(sw)
        crop_h = _even(sw / target_ar)
    crop_w, crop_h = min(crop_w, _even(sw)), min(crop_h, _even(sh))
    cx = round((sw - crop_w) * min(max(spec.crop_x, 0.0), 1.0))
    cy = round((sh - crop_h) * min(max(spec.crop_y, 0.0), 1.0))
    # Scale to the platform target size, but never upscale beyond the source pixels.
    scale = min(1.0, tw / crop_w)
    return Geometry(crop_w, crop_h, int(cx), int(cy), _even(crop_w * scale), _even(crop_h * scale))


def _watermark_font() -> str | None:
    return next((f for f in WATERMARK_FONT_CANDIDATES if Path(f).is_file()), None)


def build_video_filter(spec: RenderSpec, subtitles_path: Path | None = None) -> str:
    g = compute_geometry(spec)
    filters: list[str] = []
    if spec.fit == "pad" and spec.aspect_ratio != "original":
        filters.append(f"scale={g.out_w}:{g.out_h}:force_original_aspect_ratio=decrease")
        filters.append(f"pad={g.out_w}:{g.out_h}:(ow-iw)/2:(oh-ih)/2:color={spec.pad_color}")
    else:
        if (g.crop_w, g.crop_h) != (spec.source_width, spec.source_height):
            filters.append(f"crop={g.crop_w}:{g.crop_h}:{g.crop_x}:{g.crop_y}")
        filters.append(f"scale={g.out_w}:{g.out_h}")
    filters.append("setsar=1")
    if subtitles_path is not None:
        # Path is server-generated inside the job's temp dir; escape for filtergraph syntax.
        escaped = str(subtitles_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"subtitles='{escaped}'")
    if spec.watermark:
        font = _watermark_font()
        fontsize = max(14, g.out_h // 48)
        font_opt = f"fontfile={font}:" if font else ""
        filters.append(
            f"drawtext={font_opt}text='{WATERMARK_TEXT}':fontcolor=white@0.6:"
            f"fontsize={fontsize}:x=w-tw-{fontsize}:y=h-th-{fontsize}:"
            f"box=1:boxcolor=black@0.25:boxborderw={fontsize // 3}"
        )
    return ",".join(filters)


def build_render_command(
    spec: RenderSpec, source: Path | str, output: Path, subtitles_path: Path | None = None
) -> list[str]:
    if spec.start < 0 or spec.end <= spec.start:
        raise ValueError("invalid clip range")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y",
        "-ss",
        f"{spec.start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{spec.duration:.3f}",
        "-map",
        "0:v:0",
    ]
    if spec.has_audio:
        cmd += ["-map", "0:a:0?"]
    cmd += [
        "-vf",
        build_video_filter(spec, subtitles_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-r",
        "30",
    ]
    if spec.has_audio:
        if spec.normalize_audio:
            cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
        cmd += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
    else:
        cmd += ["-an"]
    cmd += [
        "-movflags",
        "+faststart",
        "-max_muxing_queue_size",
        "1024",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output),
    ]
    return cmd


def build_thumbnail_command(
    source: Path | str, output: Path, at_seconds: float, width: int = 640
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y",
        "-ss",
        f"{max(at_seconds, 0):.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:-2",
        "-q:v",
        "3",
        str(output),
    ]


def run_ffmpeg(
    cmd: list[str],
    *,
    duration: float | None = None,
    timeout: int = 3600,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Run ffmpeg, reporting real progress parsed from ``-progress pipe:1``."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stderr_tail: list[str] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_tail.append(line.rstrip())
            if len(stderr_tail) > 40:
                stderr_tail.pop(0)

    t = threading.Thread(target=_drain_stderr, daemon=True)
    t.start()
    started = time.monotonic()
    last_report = 0.0
    last_cancel_check = 0.0
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            now = time.monotonic()
            if now - started > timeout:
                proc.kill()
                raise ProcessingError(
                    "RENDER_TIMEOUT", "Rendering took too long and was stopped.", retryable=True
                )
            if should_cancel and now - last_cancel_check > 1.0:
                last_cancel_check = now
                if should_cancel():
                    proc.kill()
                    raise ProcessingError("CANCELLED", "The job was cancelled.")
            key, _, value = line.strip().partition("=")
            if key in ("out_time_us", "out_time_ms") and duration and on_progress:
                try:
                    seconds = int(value) / 1_000_000
                except ValueError:
                    continue
                if now - last_report > 0.5:
                    last_report = now
                    on_progress(min(max(seconds / duration, 0.0), 1.0))
        proc.wait(timeout=max(1, timeout - int(time.monotonic() - started)))
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise ProcessingError(
            "RENDER_TIMEOUT", "Rendering took too long and was stopped.", retryable=True
        ) from exc
    finally:
        if proc.poll() is None:
            proc.kill()
        t.join(timeout=2)
    if proc.returncode != 0:
        log.error("ffmpeg failed rc=%s: %s", proc.returncode, "\n".join(stderr_tail[-10:]))
        raise ProcessingError("RENDER_FAILED", "Video rendering failed.", retryable=True)
