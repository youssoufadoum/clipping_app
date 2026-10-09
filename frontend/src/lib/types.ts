export type ProjectStatus =
  | "draft"
  | "uploading"
  | "importing"
  | "queued"
  | "inspecting"
  | "ready"
  | "transcribing"
  | "analyzing"
  | "generating"
  | "rendering"
  | "completed"
  | "partially_failed"
  | "failed"
  | "cancelled"
  | "archived";

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type ClipStatus = "draft" | "queued" | "rendering" | "rendered" | "failed";
export type AspectRatio = "9:16" | "1:1" | "16:9" | "original";
export type FitMode = "crop" | "pad";

export interface Job {
  id: string;
  project_id: string;
  clip_id: string | null;
  job_type: "inspect_media" | "render_clip" | string;
  status: JobStatus;
  progress: number;
  stage: string | null;
  attempt_count: number;
  max_attempts: number;
  error_code: string | null;
  safe_error_message: string | null;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  params?: Record<string, unknown>;
}

export interface SourceMetadata {
  duration?: number;
  width?: number;
  height?: number;
  fps?: number | null;
  video_codec?: string | null;
  audio_codec?: string | null;
  has_audio?: boolean;
  format_name?: string | null;
  bit_rate?: number | null;
}

export interface Project {
  id: string;
  workspace_id: string;
  title: string;
  status: ProjectStatus;
  source_type: string;
  source_filename: string | null;
  source_size_bytes: number | null;
  source_duration_seconds: number | null;
  source_width: number | null;
  source_height: number | null;
  source_fps: number | null;
  source_mime_type: string | null;
  source_metadata: SourceMetadata;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  thumbnail_url: string | null;
  source_url?: string | null;
  has_transcript?: boolean;
  clip_count: number;
  latest_job: Job | null;
}

export interface RenderSettings {
  aspect_ratio: AspectRatio;
  fit: FitMode;
  crop_x: number;
  crop_y: number;
  pad_color: "black" | "white" | "0x111827";
  normalize_audio: boolean;
  captions?: boolean;
  caption_position?: "lower" | "middle";
}

export interface Clip {
  id: string;
  project_id: string;
  title: string;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  selection_reason: string | null;
  engagement_score: number | null;
  origin: string;
  status: ClipStatus;
  transcript_excerpt: string | null;
  render_settings: RenderSettings;
  created_at: string;
  updated_at: string;
  render_is_current: boolean;
  thumbnail_url: string | null;
  latest_job: Job | null;
}

export interface MediaAsset {
  id: string;
  project_id: string;
  clip_id: string | null;
  asset_type: string;
  mime_type: string | null;
  size_bytes: number | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Profile {
  id: string;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
  locale: string;
  creator_type: string | null;
  main_platform: string | null;
  content_category: string | null;
  caption_language: string | null;
  onboarding_completed: boolean;
  is_admin: boolean;
  plan_code: string;
  created_at: string;
}

export interface Plan {
  code: string;
  name: string;
  description: string;
  monthly_source_minutes: number;
  monthly_render_minutes: number;
  monthly_ai_minutes: number;
  max_upload_bytes: number;
  max_video_duration_seconds: number;
  max_projects: number;
  watermark: boolean;
  priority_processing: boolean;
  team_workspace: boolean;
  checkout_available: boolean;
}

export interface Usage {
  plan: Plan;
  period_start: string;
  period_end: string;
  source_minutes_used: number;
  source_minutes_limit: number;
  source_minutes_remaining: number;
  render_minutes_used: number;
  render_minutes_reserved: number;
  render_minutes_limit: number;
  render_minutes_remaining: number;
  ai_minutes_used: number;
  ai_minutes_limit: number;
  ai_minutes_remaining: number;
  policy: string[];
}

export interface UsageEvent {
  id: string;
  event_type: string;
  quantity: number;
  unit: string;
  project_id: string | null;
  job_id: string | null;
  created_at: string;
}

export interface UploadTarget {
  upload_id: string;
  method: string;
  url: string;
  headers: Record<string, string>;
  expires_in: number;
  max_bytes: number;
}

export interface SignedUrl {
  url: string;
  expires_in: number;
  filename?: string | null;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface Transcript {
  project_id: string;
  language: string | null;
  provider: string | null;
  has_word_timestamps: boolean;
  segments: TranscriptSegment[];
  updated_at: string;
}

export interface SystemStatus {
  environment: string;
  auth_mode: string;
  ai_available: boolean;
  youtube_import: boolean;
}

export interface ShortsOptions {
  target_seconds: 30 | 60;
  count: number;
  captions: boolean;
  auto_render: boolean;
}
