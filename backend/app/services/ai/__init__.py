from __future__ import annotations

from typing import Any, Protocol

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable
from app.services.ai.types import AnalysisRequest, TranscriptSegment


class AIProvider(Protocol):
    name: str

    def transcribe_chunk(
        self, audio: Any, chunk_seconds: float, language: str | None
    ) -> tuple[str | None, list[TranscriptSegment]]: ...

    def propose_clips(
        self, segments: list[TranscriptSegment], request: AnalysisRequest
    ) -> list[dict[str, Any]]: ...


def get_ai_provider() -> AIProvider:
    """The configured AI provider. Raises if none is configured — never a fake fallback."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ServiceUnavailable(
            "AI clip generation is not configured on this server (GEMINI_API_KEY is missing).",
            code="AI_NOT_CONFIGURED",
        )
    from app.services.ai.gemini import GeminiProvider

    return GeminiProvider(
        settings.gemini_api_key, settings.gemini_model, timeout=settings.gemini_timeout_seconds
    )
