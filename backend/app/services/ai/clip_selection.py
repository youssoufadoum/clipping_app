"""Turn raw model proposals into validated, non-overlapping clip candidates.

The model picks *segment ranges* (not free-form timestamps), so every clip
starts and ends on a sentence boundary from the real transcript. Durations
are then adjusted to the requested target and checked against the media.
"""

from __future__ import annotations

from typing import Any

from app.services.ai.types import AnalysisRequest, ClipCandidate, TranscriptSegment

PROMPT_TEMPLATE = """You are an expert short-form video editor.
Below is a timestamped transcript of a long video, one numbered segment per line
in the form `#index [start-end] text` (seconds).

Choose up to {count} moments that would work as standalone vertical short videos of about
{target} seconds (allowed range {min_s:.0f}-{max_s:.0f} seconds).

Rules:
- Each clip must be a contiguous range of segments: give start_segment and end_segment indices.
- A clip must make sense on its own: a complete thought, story, explanation, or answer.
  Never start mid-sentence or cut off before the point is made.
- Prefer strong hooks in the first seconds: a bold claim, surprising fact, question, emotion,
  or a clear, useful insight. Avoid greetings, sponsor reads, housekeeping and filler.
- Clips must not overlap and should cover different ideas.
- estimated_engagement_score is your 0-100 estimate of how engaging the clip is. It is an
  internal heuristic, not a prediction of views.
- title: short, catchy, under 70 characters. hook: the opening line or idea.
- selection_reason: one sentence explaining why this moment works.
- Write titles and text in the transcript's language.
{instructions}
Transcript:
{transcript}
"""

CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "clips": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "start_segment": {"type": "INTEGER"},
                    "end_segment": {"type": "INTEGER"},
                    "title": {"type": "STRING"},
                    "hook": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "selection_reason": {"type": "STRING"},
                    "topic_tags": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "estimated_engagement_score": {"type": "NUMBER"},
                    "confidence": {"type": "NUMBER"},
                    "suggested_platforms": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": [
                    "start_segment",
                    "end_segment",
                    "title",
                    "selection_reason",
                    "estimated_engagement_score",
                ],
            },
        }
    },
    "required": ["clips"],
}


def numbered_transcript(segments: list[TranscriptSegment]) -> str:
    return "\n".join(f"#{i} [{s.start:.1f}-{s.end:.1f}] {s.text}" for i, s in enumerate(segments))


def build_prompt(segments: list[TranscriptSegment], request: AnalysisRequest) -> str:
    extra = ""
    if request.instructions:
        # User text is clearly delimited and treated as a preference, not as system rules.
        prefs = request.instructions[:500]
        extra = f"- Creator preferences (follow if compatible with the rules): {prefs}\n"
    return PROMPT_TEMPLATE.format(
        count=request.count,
        target=request.target_seconds,
        min_s=request.min_seconds,
        max_s=request.max_seconds,
        instructions=extra,
        transcript=numbered_transcript(segments),
    )


def _clamp(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return min(max(f, lo), hi)


def _str(v: Any, limit: int) -> str:
    return str(v or "").strip()[:limit]


def _fit_range(
    segs: list[TranscriptSegment], a: int, b: int, request: AnalysisRequest
) -> tuple[int, int] | None:
    """Grow or shrink a segment range so its length fits the requested window."""
    dur = lambda i, j: segs[j].end - segs[i].start  # noqa: E731
    while dur(a, b) > request.max_seconds and b > a:
        b -= 1
    while dur(a, b) < request.min_seconds:
        if b + 1 < len(segs) and dur(a, b + 1) <= request.max_seconds:
            b += 1
        elif a > 0 and dur(a - 1, b) <= request.max_seconds:
            a -= 1
        else:
            break
    return (a, b)


def validate_candidates(
    raw: list[dict[str, Any]],
    segments: list[TranscriptSegment],
    media_duration: float,
    request: AnalysisRequest,
    language: str | None = None,
) -> list[ClipCandidate]:
    if not segments:
        return []
    out: list[ClipCandidate] = []
    n = len(segments)
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            a, b = int(item["start_segment"]), int(item["end_segment"])
        except (KeyError, TypeError, ValueError):
            continue
        if a > b:
            a, b = b, a
        if a < 0 or b >= n:
            continue
        fitted = _fit_range(segments, a, b, request)
        if fitted is None:
            continue
        a, b = fitted
        start = max(0.0, segments[a].start)
        end = min(media_duration, segments[b].end)
        if end - start > request.max_seconds:  # one very long segment: hard cut
            end = start + request.max_seconds
        if end - start < max(5.0, request.min_seconds * 0.6) or end <= start:
            continue
        excerpt = " ".join(s.text for s in segments[a : b + 1])
        out.append(
            ClipCandidate(
                start_time_seconds=round(start, 2),
                end_time_seconds=round(end, 2),
                title=_str(item.get("title"), 120) or "Untitled moment",
                hook=_str(item.get("hook"), 300),
                summary=_str(item.get("summary"), 600),
                transcript_excerpt=excerpt[:2000],
                selection_reason=_str(item.get("selection_reason"), 600),
                topic_tags=[_str(t, 40) for t in (item.get("topic_tags") or [])[:8] if t],
                estimated_engagement_score=round(
                    _clamp(item.get("estimated_engagement_score"), 0, 100, 50), 1
                ),
                confidence=round(_clamp(item.get("confidence"), 0, 1, 0.5), 2),
                caption_language=language,
                suggested_platforms=[
                    _str(p, 40) for p in (item.get("suggested_platforms") or [])[:6] if p
                ],
            )
        )
    # Rank by the model's estimate, then drop near-duplicates (>40% overlap).
    out.sort(key=lambda c: c.estimated_engagement_score, reverse=True)
    kept: list[ClipCandidate] = []
    for c in out:
        overlapping = False
        for k in kept:
            inter = min(c.end_time_seconds, k.end_time_seconds) - max(
                c.start_time_seconds, k.start_time_seconds
            )
            if inter > 0.4 * min(c.duration_seconds, k.duration_seconds):
                overlapping = True
                break
        if not overlapping:
            kept.append(c)
    return kept[: request.count]


def clean_segments(
    raw: list[dict[str, Any]], offset: float, chunk_seconds: float
) -> list[TranscriptSegment]:
    """Validate model-produced segments for one audio chunk and shift them to source time."""
    segs: list[TranscriptSegment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or "").split())
        try:
            start, end = float(item["start"]), float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if not text or end <= start or start < 0 or start > chunk_seconds + 1:
            continue
        end = min(end, chunk_seconds + 0.5)
        segs.append(
            TranscriptSegment(round(start + offset, 2), round(end + offset, 2), text[:1000])
        )
    segs.sort(key=lambda s: s.start)
    # Remove overlaps between consecutive segments.
    for prev, cur in zip(segs, segs[1:], strict=False):
        if cur.start < prev.end:
            prev.end = max(prev.start + 0.1, cur.start)
    return segs
