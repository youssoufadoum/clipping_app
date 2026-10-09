export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const total = Math.max(0, seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = Math.floor(total % 60);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/** Timecode with tenths, e.g. 1:05.3 — used in the editor. */
export function formatTimecode(seconds: number): string {
  const total = Math.max(0, seconds);
  const m = Math.floor(total / 60);
  const s = total - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

/** Parse "m:ss.s", "h:mm:ss" or plain seconds. Returns null when invalid. */
export function parseTimecode(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parts = trimmed.split(":");
  if (parts.length > 3) return null;
  let total = 0;
  for (const part of parts) {
    if (!/^\d+(\.\d+)?$/.test(part)) return null;
    total = total * 60 + Number(part);
  }
  return Number.isFinite(total) ? total : null;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatMinutes(minutes: number): string {
  return `${minutes.toLocaleString(undefined, { maximumFractionDigits: 1 })} min`;
}

const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting in queue",
  verifying_file: "Verifying file",
  probing: "Reading video details",
  generating_thumbnail: "Creating thumbnail",
  finalizing: "Finalizing",
  preparing: "Preparing",
  rendering: "Rendering",
  validating_output: "Checking output",
  uploading: "Saving export",
  retry_scheduled: "Retrying shortly",
  extracting_audio: "Extracting audio",
  transcribing: "Transcribing speech",
  finding_moments: "AI is finding the best moments",
  creating_clips: "Creating your shorts",
  recovered: "Resuming after interruption",
  completed: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "";
  return STAGE_LABELS[stage] ?? stage.replace(/_/g, " ");
}
