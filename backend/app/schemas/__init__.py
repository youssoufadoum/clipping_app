from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):  # noqa: UP046 - pydantic generic
    items: list[T]
    total: int
    page: int
    page_size: int


# --- Auth / profile -----------------------------------------------------


class LocalCredentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    user_id: uuid.UUID
    email: str


class SessionInfo(BaseModel):
    user_id: uuid.UUID
    email: str | None
    provider: str


class ProfileOut(ORM):
    id: uuid.UUID
    email: str | None
    display_name: str | None
    avatar_url: str | None
    locale: str
    creator_type: str | None
    main_platform: str | None
    content_category: str | None
    caption_language: str | None
    onboarding_completed: bool
    is_admin: bool
    plan_code: str
    created_at: datetime


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    avatar_url: str | None = Field(default=None, max_length=1024)
    locale: str | None = Field(default=None, max_length=16)
    creator_type: str | None = Field(default=None, max_length=64)
    main_platform: str | None = Field(default=None, max_length=64)
    content_category: str | None = Field(default=None, max_length=64)
    caption_language: str | None = Field(default=None, max_length=16)
    onboarding_completed: bool | None = None

    @field_validator("avatar_url")
    @classmethod
    def _https_only(cls, v: str | None) -> str | None:
        if v and not v.startswith("https://"):
            raise ValueError("avatar_url must be an https URL")
        return v


class AccountDeletion(BaseModel):
    confirm: Literal["DELETE"]


# --- Projects -------------------------------------------------------------


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be blank")
        return v


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None


class JobOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    clip_id: uuid.UUID | None
    job_type: str
    status: str
    progress: float
    stage: str | None
    attempt_count: int
    max_attempts: int
    error_code: str | None
    safe_error_message: str | None
    cancel_requested: bool
    params: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class ProjectOut(ORM):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: str
    source_type: str
    source_filename: str | None
    source_size_bytes: int | None
    source_duration_seconds: float | None
    source_width: int | None
    source_height: int | None
    source_fps: float | None
    source_mime_type: str | None
    source_metadata: dict[str, Any]
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    thumbnail_url: str | None = None
    source_url: str | None = None
    has_transcript: bool = False
    clip_count: int = 0
    latest_job: JobOut | None = None


# --- Uploads --------------------------------------------------------------


class UploadInitiate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(max_length=128)
    size_bytes: int = Field(gt=0)


class UploadTargetOut(BaseModel):
    upload_id: uuid.UUID
    method: str
    url: str
    headers: dict[str, str]
    expires_in: int
    max_bytes: int


class AutoShorts(BaseModel):
    target_seconds: Literal[30, 60] = 30
    count: int = Field(default=3, ge=1, le=5)
    captions: bool = True
    auto_render: bool = True


class AnalyzeRequest(AutoShorts):
    instructions: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, max_length=16, pattern=r"^[a-zA-Z-]{2,16}$")


class ImportUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    rights_confirmed: bool
    title: str | None = Field(default=None, max_length=200)
    auto_shorts: AutoShorts | None = None


class UploadComplete(BaseModel):
    upload_id: uuid.UUID
    auto_shorts: AutoShorts | None = None


class UploadCompleteOut(BaseModel):
    project: ProjectOut
    job: JobOut


class MediaOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    clip_id: uuid.UUID | None
    asset_type: str
    mime_type: str | None
    size_bytes: int | None
    duration_seconds: float | None
    width: int | None
    height: int | None
    created_at: datetime


# --- Clips ----------------------------------------------------------------

AspectRatio = Literal["9:16", "1:1", "16:9", "original"]


class RenderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect_ratio: AspectRatio = "9:16"
    fit: Literal["crop", "pad"] = "crop"
    crop_x: float = Field(default=0.5, ge=0.0, le=1.0)
    crop_y: float = Field(default=0.5, ge=0.0, le=1.0)
    pad_color: Literal["black", "white", "0x111827"] = "black"
    normalize_audio: bool = False
    captions: bool = False
    caption_position: Literal["lower", "middle"] = "lower"


class ClipCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    render_settings: RenderSettings = Field(default_factory=RenderSettings)

    @model_validator(mode="after")
    def _range(self) -> ClipCreate:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class ClipUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)
    render_settings: RenderSettings | None = None


class ClipOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    selection_reason: str | None
    engagement_score: float | None
    origin: str
    status: str
    transcript_excerpt: str | None
    render_settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    render_is_current: bool = False
    thumbnail_url: str | None = None
    latest_job: JobOut | None = None


class TranscriptSegmentOut(BaseModel):
    start: float
    end: float
    text: str


class TranscriptOut(ORM):
    project_id: uuid.UUID
    language: str | None
    provider: str | None
    has_word_timestamps: bool
    segments: list[TranscriptSegmentOut]
    updated_at: datetime


class TranscriptEdit(BaseModel):
    index: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=1000)


class TranscriptUpdate(BaseModel):
    segments: list[TranscriptEdit] = Field(min_length=1, max_length=5000)


class SignedUrlOut(BaseModel):
    url: str
    expires_in: int
    filename: str | None = None


# --- Usage / billing ------------------------------------------------------


class PlanOut(BaseModel):
    code: str
    name: str
    description: str
    monthly_source_minutes: int
    monthly_render_minutes: int
    monthly_ai_minutes: int
    max_upload_bytes: int
    max_video_duration_seconds: int
    max_projects: int
    watermark: bool
    priority_processing: bool
    team_workspace: bool
    checkout_available: bool


class UsageOut(BaseModel):
    plan: PlanOut
    period_start: datetime
    period_end: datetime
    source_minutes_used: float
    source_minutes_limit: int
    source_minutes_remaining: float
    render_minutes_used: float
    render_minutes_reserved: float
    render_minutes_limit: int
    render_minutes_remaining: float
    ai_minutes_used: float
    ai_minutes_limit: int
    ai_minutes_remaining: float
    policy: list[str]


class UsageEventOut(ORM):
    id: uuid.UUID
    event_type: str
    quantity: float
    unit: str
    project_id: uuid.UUID | None
    job_id: uuid.UUID | None
    created_at: datetime


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody
