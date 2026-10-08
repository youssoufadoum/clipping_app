from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_\-.]{0,1000}$")


def validate_key(key: str) -> str:
    """Storage keys are generated server side; reject anything unexpected."""
    if not _SAFE_KEY.match(key) or ".." in key or "//" in key:
        raise ValueError("invalid storage key")
    return key


@dataclass
class UploadTarget:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    expires_in: int = 900


@dataclass
class ObjectInfo:
    size: int
    content_type: str | None


class StorageProvider(ABC):
    name: str

    @abstractmethod
    def create_upload(
        self, key: str, content_type: str, size_bytes: int, ttl: int
    ) -> UploadTarget: ...

    @abstractmethod
    def head(self, key: str) -> ObjectInfo | None: ...

    @abstractmethod
    def read_prefix(self, key: str, length: int) -> bytes: ...

    @abstractmethod
    def download_to(self, key: str, dest: Path) -> None: ...

    @abstractmethod
    def upload_file(self, src: Path, key: str, content_type: str) -> None: ...

    @abstractmethod
    def signed_download_url(
        self, key: str, ttl: int, filename: str | None = None, inline: bool = True
    ) -> str: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int: ...

    @abstractmethod
    def ffmpeg_input(self, key: str, ttl: int) -> str:
        """A path or short-lived URL FFmpeg can read (with seeking) without a full download."""

    def check(self) -> bool:
        """Lightweight readiness check."""
        return True
