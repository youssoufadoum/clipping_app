"""Provider-independent AI types and interfaces.

Providers return raw model output; everything is validated against the real
media (durations, segment boundaries) before it is stored or shown.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptResult:
    language: str | None
    segments: list[TranscriptSegment]
    provider: str
    # Gemini returns phrase-level timestamps only; never claim word timing we don't have.
    has_word_timestamps: bool = False


@dataclass
class AnalysisRequest:
    target_seconds: int  # 30 or 60
    count: int = 3
    instructions: str | None = None

    @property
    def min_seconds(self) -> float:
        return (
            self.target_seconds * (2 / 3)
            if self.target_seconds <= 30
            else self.target_seconds * 0.75
        )

    @property
    def max_seconds(self) -> float:
        return (
            self.target_seconds * (4 / 3)
            if self.target_seconds <= 30
            else self.target_seconds * 1.25
        )


@dataclass
class ClipCandidate:
    start_time_seconds: float
    end_time_seconds: float
    title: str
    hook: str
    summary: str
    transcript_excerpt: str
    selection_reason: str
    topic_tags: list[str] = field(default_factory=list)
    estimated_engagement_score: float = 0.0
    confidence: float = 0.0
    caption_language: str | None = None
    suggested_platforms: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return round(self.end_time_seconds - self.start_time_seconds, 3)


class TranscriptionProvider(Protocol):
    name: str

    def transcribe_chunk(
        self, audio: Path, chunk_seconds: float, language: str | None
    ) -> tuple[str | None, list[TranscriptSegment]]: ...


class ClipAnalysisProvider(Protocol):
    name: str

    def propose_clips(
        self, segments: list[TranscriptSegment], request: AnalysisRequest
    ) -> list[dict[str, Any]]: ...
