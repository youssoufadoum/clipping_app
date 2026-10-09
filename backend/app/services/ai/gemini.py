"""Google Gemini provider (REST, no SDK) for transcription and clip analysis.

All calls run on the server with the API key in a header. Responses are
requested as JSON with a response schema and then validated again locally;
malformed output is retried once and otherwise reported as an error, never
replaced with made-up data.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.errors import ProcessingError
from app.services.ai.clip_selection import CANDIDATE_SCHEMA, build_prompt, clean_segments
from app.services.ai.types import AnalysisRequest, TranscriptSegment

log = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_INLINE_BYTES = 18 * 1024 * 1024

TRANSCRIPT_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "language": {"type": "STRING"},
        "segments": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "start": {"type": "NUMBER"},
                    "end": {"type": "NUMBER"},
                    "text": {"type": "STRING"},
                },
                "required": ["start", "end", "text"],
            },
        },
    },
    "required": ["segments"],
}

TRANSCRIBE_PROMPT = """Transcribe all speech in this audio accurately,
with punctuation and capitalization. Return JSON with:
- language: the ISO 639-1 code of the main spoken language
- segments: consecutive phrases of one sentence or at most ~8 seconds each, with start and end
  times in seconds measured from the beginning of THIS audio file
  (the file is {seconds:.0f} seconds long).
Transcribe only what is said; do not summarize, translate or invent words. If there is no speech,
return an empty segments list.{language_hint}"""


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 300,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(timeout, connect=15),
            transport=transport,
        )
        self.model = model

    # --- low level ----------------------------------------------------------
    def _generate(
        self, parts: list[dict[str, Any]], schema: dict[str, Any], temperature: float
    ) -> Any:
        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        last_error: ProcessingError | None = None
        for attempt in range(3):
            try:
                resp = self._client.post(f"/models/{self.model}:generateContent", json=body)
            except httpx.TimeoutException:
                last_error = ProcessingError(
                    "AI_TIMEOUT", "The AI service took too long to respond.", retryable=True
                )
                continue
            except httpx.HTTPError:
                last_error = ProcessingError(
                    "AI_UNAVAILABLE", "The AI service could not be reached.", retryable=True
                )
                time.sleep(2**attempt)
                continue
            if resp.status_code in (400, 401, 403):
                detail = _error_status(resp)
                log.error("gemini rejected request status=%s detail=%s", resp.status_code, detail)
                if "API_KEY" in detail or resp.status_code in (401, 403):
                    raise ProcessingError(
                        "AI_AUTH_FAILED", "The AI service rejected this server's API key."
                    )
                raise ProcessingError(
                    "AI_BAD_REQUEST", "The AI service could not process this video."
                )
            if resp.status_code == 404:
                raise ProcessingError(
                    "AI_MODEL_NOT_FOUND", "The configured AI model is not available."
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = ProcessingError(
                    "AI_RATE_LIMITED" if resp.status_code == 429 else "AI_UNAVAILABLE",
                    "The AI service is busy. We'll retry automatically.",
                    retryable=True,
                )
                time.sleep(min(2 ** (attempt + 1), 10))
                continue
            data = resp.json()
            text = _response_text(data)
            if text is None:
                raise ProcessingError(
                    "AI_BLOCKED", "The AI service declined to process this content."
                )
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                log.warning("gemini returned malformed JSON (attempt %s)", attempt + 1)
                last_error = ProcessingError(
                    "AI_INVALID_RESPONSE",
                    "The AI service returned an unreadable answer.",
                    retryable=True,
                )
        assert last_error is not None
        raise last_error

    # --- transcription ----------------------------------------------------
    def transcribe_chunk(
        self, audio: Path, chunk_seconds: float, language: str | None
    ) -> tuple[str | None, list[TranscriptSegment]]:
        data = audio.read_bytes()
        if len(data) > MAX_INLINE_BYTES:
            raise ProcessingError("AUDIO_TOO_LARGE", "An audio chunk was too large to transcribe.")
        hint = f"\nThe speaker is expected to use language code '{language}'." if language else ""
        result = self._generate(
            [
                {
                    "inline_data": {
                        "mime_type": "audio/mp3",
                        "data": base64.b64encode(data).decode(),
                    }
                },
                {"text": TRANSCRIBE_PROMPT.format(seconds=chunk_seconds, language_hint=hint)},
            ],
            TRANSCRIPT_SCHEMA,
            temperature=0.0,
        )
        if not isinstance(result, dict):
            raise ProcessingError(
                "AI_INVALID_RESPONSE", "The transcript could not be read.", retryable=True
            )
        lang = result.get("language")
        segments = clean_segments(result.get("segments") or [], 0.0, chunk_seconds)
        return (str(lang)[:16] if lang else None), segments

    # --- clip analysis ----------------------------------------------------
    def propose_clips(
        self, segments: list[TranscriptSegment], request: AnalysisRequest
    ) -> list[dict[str, Any]]:
        result = self._generate(
            [{"text": build_prompt(segments, request)}], CANDIDATE_SCHEMA, temperature=0.4
        )
        if not isinstance(result, dict) or not isinstance(result.get("clips"), list):
            raise ProcessingError(
                "AI_INVALID_RESPONSE", "The AI returned no usable clips.", retryable=True
            )
        return result["clips"]


def _response_text(data: dict[str, Any]) -> str | None:
    for cand in data.get("candidates") or []:
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if text:
            return text
    return None


def _error_status(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error", {})
        reasons = " ".join(
            d.get("reason", "") for d in err.get("details", []) if isinstance(d, dict)
        )
        return f"{err.get('status', '')} {reasons}".strip()
    except Exception:  # noqa: BLE001
        return ""
