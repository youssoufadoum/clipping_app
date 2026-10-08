"""Structured JSON logging with correlation IDs and secret redaction."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

_REDACTIONS = [
    # Signed URL query parameters (S3 and local signer)
    (
        re.compile(r"(X-Amz-(?:Signature|Credential|Security-Token)=)[^&\s\"]+", re.I),
        r"\1[REDACTED]",
    ),
    (re.compile(r"([?&]token=)[^&\s\"]+"), r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.=]+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(sk|rk|pk)_(live|test)_[A-Za-z0-9]+"), "[REDACTED_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9\-_]{16,}"), "[REDACTED_KEY]"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        cid = correlation_id_var.get()
        if cid:
            payload["correlation_id"] = cid
        for key in ("job_id", "project_id", "clip_id", "user_id", "path", "status", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = str(value)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True
