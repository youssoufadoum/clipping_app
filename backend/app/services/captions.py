"""Caption cues from transcript segments, rendered as ASS (burn-in), SRT and VTT.

The transcript has phrase-level timestamps, so each phrase is split into short
caption chunks whose timing is distributed by character count within the
phrase. This is an approximation and is labeled as such in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

MAX_WORDS = 4
MAX_CHARS = 24


@dataclass
class Cue:
    start: float
    end: float
    text: str


def _chunks(text: str) -> list[str]:
    words = text.split()
    out: list[str] = []
    cur: list[str] = []
    for w in words:
        if cur and (len(cur) >= MAX_WORDS or len(" ".join([*cur, w])) > MAX_CHARS):
            out.append(" ".join(cur))
            cur = []
        cur.append(w)
    if cur:
        out.append(" ".join(cur))
    return out


def build_cues(segments: list[dict[str, Any]], clip_start: float, clip_end: float) -> list[Cue]:
    """Cues relative to the clip start, limited to [0, clip duration]."""
    duration = clip_end - clip_start
    cues: list[Cue] = []
    for seg in segments:
        try:
            s, e, text = float(seg["start"]), float(seg["end"]), str(seg.get("text") or "")
        except (KeyError, TypeError, ValueError):
            continue
        if e <= clip_start or s >= clip_end or not text.strip() or e <= s:
            continue
        parts = _chunks(text)
        total = sum(len(p) for p in parts) or 1
        t = s
        for p in parts:
            span = (e - s) * len(p) / total
            cs, ce = t - clip_start, t + span - clip_start
            t += span
            cs, ce = max(cs, 0.0), min(ce, duration)
            if ce - cs >= 0.15:
                cues.append(Cue(round(cs, 2), round(ce, 2), p))
    return cues


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def _ass_text(text: str) -> str:
    # Neutralize ASS override syntax so transcript text is always plain text.
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def to_ass(
    cues: list[Cue], width: int, height: int, position: Literal["lower", "middle"] = "lower"
) -> str:
    portrait = height > width
    fontsize = max(16, round(height * (0.048 if portrait else 0.06)))
    outline = max(2, round(fontsize * 0.09))
    alignment = 2 if position == "lower" else 5
    margin_v = round(height * (0.2 if portrait else 0.1)) if position == "lower" else 0
    margin_h = round(width * 0.06)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,DejaVu Sans,{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},1,{alignment},{margin_h},{margin_h},{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    lines += [
        f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},Default,,0,0,0,,{_ass_text(c.text)}"
        for c in cues
    ]
    return "\n".join(lines) + "\n"


def _srt_time(t: float, sep: str) -> str:
    ms = int(round(t * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    blocks = [
        f"{i}\n{_srt_time(c.start, ',')} --> {_srt_time(c.end, ',')}\n{c.text}\n"
        for i, c in enumerate(cues, 1)
    ]
    return "\n".join(blocks)


def to_vtt(cues: list[Cue]) -> str:
    blocks = [f"{_srt_time(c.start, '.')} --> {_srt_time(c.end, '.')}\n{c.text}\n" for c in cues]
    return "WEBVTT\n\n" + "\n".join(blocks)
