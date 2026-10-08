from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.storage.base import ObjectInfo, StorageProvider, UploadTarget, validate_key


@lru_cache
def get_storage() -> StorageProvider:
    settings = get_settings()
    if settings.storage_backend == "local":
        from app.services.storage.local import LocalStorage

        return LocalStorage(
            settings.local_storage_path, settings.secret_key, settings.backend_public_url
        )
    from app.services.storage.s3 import S3Storage

    if not settings.s3_bucket_name:
        raise RuntimeError("S3_BUCKET_NAME is required when STORAGE_BACKEND=s3")
    return S3Storage(
        bucket=settings.s3_bucket_name,
        region=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
    )


def project_prefix(owner_id: object, project_id: object) -> str:
    return f"users/{owner_id}/projects/{project_id}/"


__all__ = [
    "ObjectInfo",
    "StorageProvider",
    "UploadTarget",
    "get_storage",
    "project_prefix",
    "validate_key",
]
