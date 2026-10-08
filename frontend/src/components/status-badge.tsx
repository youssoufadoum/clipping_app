import type { ClipStatus, JobStatus, ProjectStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

type AnyStatus = ProjectStatus | JobStatus | ClipStatus;

const STYLES: Record<string, { label: string; cls: string }> = {
  draft: { label: "Draft", cls: "bg-surface-2 text-muted" },
  uploading: { label: "Uploading", cls: "bg-accent-soft text-accent" },
  queued: { label: "Queued", cls: "bg-accent-soft text-accent" },
  inspecting: { label: "Processing", cls: "bg-accent-soft text-accent" },
  running: { label: "Running", cls: "bg-accent-soft text-accent" },
  rendering: { label: "Rendering", cls: "bg-accent-soft text-accent" },
  transcribing: { label: "Transcribing", cls: "bg-accent-soft text-accent" },
  analyzing: { label: "Analyzing", cls: "bg-accent-soft text-accent" },
  generating: { label: "Generating", cls: "bg-accent-soft text-accent" },
  ready: { label: "Ready", cls: "bg-success-soft text-success" },
  rendered: { label: "Rendered", cls: "bg-success-soft text-success" },
  succeeded: { label: "Succeeded", cls: "bg-success-soft text-success" },
  completed: { label: "Completed", cls: "bg-success-soft text-success" },
  partially_failed: { label: "Partially failed", cls: "bg-warning-soft text-warning" },
  failed: { label: "Failed", cls: "bg-danger-soft text-danger" },
  cancelled: { label: "Cancelled", cls: "bg-surface-2 text-muted" },
  archived: { label: "Archived", cls: "bg-surface-2 text-muted" },
};

export const ACTIVE_STATUSES = new Set(["uploading", "queued", "inspecting", "running", "rendering", "transcribing", "analyzing", "generating"]);

export function StatusBadge({ status, className }: { status: AnyStatus; className?: string }) {
  const style = STYLES[status] ?? { label: status, cls: "bg-surface-2 text-muted" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium", style.cls, className)}>
      {ACTIVE_STATUSES.has(status) && <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />}
      {style.label}
    </span>
  );
}
