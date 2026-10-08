"""S3-compatible object storage (Amazon S3, Cloudflare R2, MinIO, ...).

Buckets must be private. Browsers only ever receive short-lived presigned URLs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.services.storage.base import ObjectInfo, StorageProvider, UploadTarget, validate_key


class S3Storage(StorageProvider):
    name = "s3"

    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
    ) -> None:
        self.bucket = bucket
        self.client: Any = boto3.client(
            "s3",
            region_name=region or "auto",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 5, "mode": "standard"},
                connect_timeout=10,
                read_timeout=120,
            ),
        )

    def create_upload(self, key: str, content_type: str, size_bytes: int, ttl: int) -> UploadTarget:
        url = self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": validate_key(key), "ContentType": content_type},
            ExpiresIn=ttl,
            HttpMethod="PUT",
        )
        return UploadTarget(
            method="PUT", url=url, headers={"Content-Type": content_type}, expires_in=ttl
        )

    def head(self, key: str) -> ObjectInfo | None:
        try:
            resp = self.client.head_object(Bucket=self.bucket, Key=validate_key(key))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return ObjectInfo(size=int(resp["ContentLength"]), content_type=resp.get("ContentType"))

    def read_prefix(self, key: str, length: int) -> bytes:
        resp = self.client.get_object(
            Bucket=self.bucket, Key=validate_key(key), Range=f"bytes=0-{length - 1}"
        )
        data: bytes = resp["Body"].read()
        return data

    def download_to(self, key: str, dest: Path) -> None:
        self.client.download_file(self.bucket, validate_key(key), str(dest))

    def upload_file(self, src: Path, key: str, content_type: str) -> None:
        self.client.upload_file(
            str(src), self.bucket, validate_key(key), ExtraArgs={"ContentType": content_type}
        )

    def signed_download_url(
        self, key: str, ttl: int, filename: str | None = None, inline: bool = True
    ) -> str:
        params: dict[str, str] = {"Bucket": self.bucket, "Key": validate_key(key)}
        if filename:
            disposition = "inline" if inline else "attachment"
            safe = filename.replace('"', "")
            params["ResponseContentDisposition"] = f'{disposition}; filename="{safe}"'
        url: str = self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=ttl)
        return url

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=validate_key(key))

    def delete_prefix(self, prefix: str) -> int:
        validate_key(prefix.rstrip("/"))
        deleted = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})
                deleted += len(objects)
        return deleted

    def ffmpeg_input(self, key: str, ttl: int) -> str:
        return self.signed_download_url(key, ttl)

    def check(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except ClientError:
            return False
