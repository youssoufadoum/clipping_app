"""Application configuration loaded from environment variables.

Secrets are only ever read from the environment (or a secret manager that
injects environment variables). Nothing here is exposed to the browser.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    api_secret_key: str = Field(default="", description="Signs local storage URLs and dev tokens")
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://virello:virello@localhost:5432/virello"
    redis_url: str = "redis://localhost:6379/0"

    # --- Authentication -------------------------------------------------
    # "supabase": verify Supabase-issued JWTs (production).
    # "local": a development-only email/password provider implemented by this
    #          backend so the app can be exercised without a Supabase project.
    auth_mode: Literal["supabase", "local"] = "supabase"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_jwks_url: str = ""
    supabase_jwt_secret: str = ""  # legacy HS256 projects only
    supabase_jwt_audience: str = "authenticated"
    admin_emails: str = ""  # comma separated list of administrator emails

    # --- Storage ----------------------------------------------------------
    storage_backend: Literal["s3", "local"] = "s3"
    local_storage_path: str = "./var/storage"
    s3_endpoint_url: str = ""
    s3_bucket_name: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_signed_url_ttl_seconds: int = 900

    # --- URLs -----------------------------------------------------------
    frontend_url: str = "http://localhost:3000"
    backend_public_url: str = "http://localhost:8000"
    cors_origins: str = ""

    # --- Limits -----------------------------------------------------------
    max_upload_bytes: int = 5 * 1024 * 1024 * 1024
    max_video_duration_seconds: int = 4 * 60 * 60
    max_render_concurrency: int = 2
    media_retention_days: int = 30
    ffmpeg_timeout_seconds: int = 60 * 60
    work_dir: str = "./var/work"

    # --- Observability --------------------------------------------------
    sentry_dsn: str = ""
    metrics_token: str = ""

    # --- Optional providers (later phases) ------------------------------
    openai_api_key: str = ""
    openai_transcription_model: str = ""
    openai_analysis_model: str = ""
    gemini_api_key: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    resend_api_key: str = ""
    email_from: str = ""

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.app_env == "production":
            if self.auth_mode == "local":
                raise ValueError("AUTH_MODE=local is not allowed in production")
            if len(self.api_secret_key) < 32:
                raise ValueError("API_SECRET_KEY must be at least 32 characters in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def secret_key(self) -> str:
        if self.api_secret_key:
            return self.api_secret_key
        if self.app_env in ("development", "test"):
            return "insecure-development-secret-change-me-0123456789"
        raise RuntimeError("API_SECRET_KEY is not configured")

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return origins or [self.frontend_url]

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
