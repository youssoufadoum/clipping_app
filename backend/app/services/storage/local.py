"""Filesystem storage for development and single-node deployments.

Uploads and downloads go through short-lived HMAC-signed URLs served by the
API (``/api/v1/storage/local/...``), mirroring the presigned-URL flow used
with S3 so the frontend code path is identical.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from app.services.storage.base import ObjectInfo, StorageProvider, UploadTarget, validate_key


class LocalStorage(StorageProvider):
    name = "local"

    def __init__(self, root: str, secret: str, public_base_url: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._secret = secret.encode()
        self._base = public_base_url.rstrip("/")

    # --- signing ------------------------------------------------------
    def sign(self, payload: dict[str, object]) -> str:
        body = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
        sig = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def verify(self, token: str, op: str) -> dict[str, object]:
        try:
            body, sig = token.rsplit(".", 1)
        except ValueError as exc:
            raise PermissionError("malformed token") from exc
        expected = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise PermissionError("bad signature")
        payload = json.loads(base64.urlsafe_b64decode(body.encode()))
        if payload.get("op") != op:
            raise PermissionError("wrong operation")
        if float(payload.get("exp", 0)) < time.time():
            raise PermissionError("expired")
        validate_key(str(payload["key"]))
        return payload

    def path_for(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid storage key")
        return path

    # --- provider API ---------------------------------------------------
    def create_upload(self, key: str, content_type: str, size_bytes: int, ttl: int) -> UploadTarget:
        token = self.sign(
            {
                "op": "put",
                "key": key,
                "exp": time.time() + ttl,
                "max": size_bytes,
                "ct": content_type,
            }
        )
        return UploadTarget(
            method="PUT",
            url=f"{self._base}/api/v1/storage/local/upload?token={quote(token)}",
            headers={"Content-Type": content_type},
            expires_in=ttl,
        )

    def head(self, key: str) -> ObjectInfo | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        return ObjectInfo(size=path.stat().st_size, content_type=None)

    def read_prefix(self, key: str, length: int) -> bytes:
        with self.path_for(key).open("rb") as fh:
            return fh.read(length)

    def download_to(self, key: str, dest: Path) -> None:
        shutil.copyfile(self.path_for(key), dest)

    def upload_file(self, src: Path, key: str, content_type: str) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, path)

    def signed_download_url(
        self, key: str, ttl: int, filename: str | None = None, inline: bool = True
    ) -> str:
        token = self.sign(
            {
                "op": "get",
                "key": key,
                "exp": time.time() + ttl,
                "fn": filename or "",
                "inline": inline,
            }
        )
        return f"{self._base}/api/v1/storage/local/object?token={quote(token)}"

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> int:
        target = self.path_for(prefix.rstrip("/"))
        if not target.exists():
            return 0
        count = sum(1 for p in target.rglob("*") if p.is_file())
        shutil.rmtree(target)
        return count

    def ffmpeg_input(self, key: str, ttl: int) -> str:
        return str(self.path_for(key))

    def check(self) -> bool:
        return self.root.is_dir()
