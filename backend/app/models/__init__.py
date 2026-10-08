"""SQLAlchemy ORM models.

The schema mirrors the Alembic migrations in ``alembic/versions``. Ownership is
enforced in the API layer for every request, and Row Level Security policies
(applied when the database is a Supabase project) provide defense in depth for
any client that talks to PostgREST directly with the anon key.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class ProjectStatus(enum.StrEnum):
    draft = "draft"
    uploading = "uploading"
    queued = "queued"
    inspecting = "inspecting"
    ready = "ready"  # source stored and inspected; clips can be created
    transcribing = "transcribing"
    analyzing = "analyzing"
    generating = "generating"
    rendering = "rendering"
    completed = "completed"
    partially_failed = "partially_failed"
    failed = "failed"
    cancelled = "cancelled"
    archived = "archived"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobType(enum.StrEnum):
    inspect_media = "inspect_media"
    render_clip = "render_clip"
    transcribe = "transcribe"
    analyze = "analyze"


class ClipStatus(enum.StrEnum):
    draft = "draft"
    queued = "queued"
    rendering = "rendering"
    rendered = "rendered"
    failed = "failed"


class AssetType(enum.StrEnum):
    source_video = "source_video"
    thumbnail = "thumbnail"
    rendered_clip = "rendered_clip"
    clip_thumbnail = "clip_thumbnail"
    audio = "audio"
    subtitle = "subtitle"


TZ = DateTime(timezone=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZ, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    locale: Mapped[str] = mapped_column(String(16), default="en", server_default="en")
    creator_type: Mapped[str | None] = mapped_column(String(64))
    main_platform: Mapped[str | None] = mapped_column(String(64))
    content_category: Mapped[str | None] = mapped_column(String(64))
    caption_language: Mapped[str | None] = mapped_column(String(16))
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    plan_code: Mapped[str] = mapped_column(String(32), default="free", server_default="free")


class LocalAuthUser(TimestampMixin, Base):
    """Credentials for the development-only local auth provider (AUTH_MODE=local)."""

    __tablename__ = "local_auth_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_personal: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(32), default="owner", nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now(), nullable=False)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_owner_created", "owner_id", "created_at"),
        Index("ix_projects_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="upload", nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(512))
    source_storage_key: Mapped[str | None] = mapped_column(String(1024))
    source_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    source_duration_seconds: Mapped[float | None] = mapped_column(Float)
    source_width: Mapped[int | None] = mapped_column(Integer)
    source_height: Mapped[int | None] = mapped_column(Integer)
    source_fps: Mapped[float | None] = mapped_column(Float)
    source_mime_type: Mapped[str | None] = mapped_column(String(128))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.draft, nullable=False)
    processing_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    archived_at: Mapped[datetime | None] = mapped_column(TZ)

    clips: Mapped[list[Clip]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class ProcessingJob(TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("ix_jobs_project_created", "project_id", "created_at"),
        Index("ix_jobs_status_created", "status", "created_at"),
        UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    clip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), index=True
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.queued, nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    stage: Mapped[str | None] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(Text)
    provider_job_id: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    started_at: Mapped[datetime | None] = mapped_column(TZ)
    completed_at: Mapped[datetime | None] = mapped_column(TZ)


class Transcript(TimestampMixin, Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    language: Mapped[str | None] = mapped_column(String(16))
    full_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    provider: Mapped[str | None] = mapped_column(String(64))
    has_word_timestamps: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")


class Clip(TimestampMixin, Base):
    __tablename__ = "clips"
    __table_args__ = (Index("ix_clips_project_created", "project_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    selection_reason: Mapped[str | None] = mapped_column(Text)
    engagement_score: Mapped[float | None] = mapped_column(Float)
    origin: Mapped[str] = mapped_column(String(32), default="manual", server_default="manual")
    status: Mapped[str] = mapped_column(String(32), default=ClipStatus.draft, nullable=False)
    transcript_excerpt: Mapped[str | None] = mapped_column(Text)
    render_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    rendered_settings_hash: Mapped[str | None] = mapped_column(String(64))

    project: Mapped[Project] = relationship(back_populates="clips")


class CaptionSegment(Base):
    __tablename__ = "caption_segments"
    __table_args__ = (Index("ix_caption_segments_clip_order", "clip_id", "sort_order"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), nullable=False
    )
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    style: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        Index("ix_media_assets_project_type", "project_id", "asset_type"),
        Index("ix_media_assets_clip", "clip_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    clip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="SET NULL")
    )
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now(), nullable=False)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_usage_idempotency_key"),
        Index("ix_usage_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now(), nullable=False)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL")
    )
    billing_provider: Mapped[str] = mapped_column(String(32), default="stripe")
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), index=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(TZ)
    current_period_end: Mapped[datetime | None] = mapped_column(TZ)


class BrandTemplate(TimestampMixin, Base):
    __tablename__ = "brand_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    logo_storage_key: Mapped[str | None] = mapped_column(String(1024))
    caption_style: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    intro_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    outro_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class SocialAccount(TimestampMixin, Base):
    __tablename__ = "social_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Reference into a secret store / ciphertext; never a plain-text token.
    encrypted_token_reference: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(TZ)
    scopes: Mapped[str | None] = mapped_column(Text)
    connection_status: Mapped[str] = mapped_column(String(32), default="connected")


class ScheduledPost(TimestampMixin, Base):
    __tablename__ = "scheduled_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(TZ, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    provider_post_id: Mapped[str | None] = mapped_column(String(255))
    safe_error_message: Mapped[str | None] = mapped_column(Text)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(TZ)
    status: Mapped[str] = mapped_column(String(32), default="received")
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now(), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_actor_created", "actor_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now(), nullable=False)
