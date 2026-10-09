"use client";

import { useQueryClient } from "@tanstack/react-query";
import { FileVideo, RotateCcw, Sparkles, UploadCloud, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Progress } from "@/components/ui/feedback";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { useSystemStatus, useUsage } from "@/lib/queries";
import type { Project, UploadTarget } from "@/lib/types";
import { ACCEPT_ATTR, contentTypeFor, putToStorage, validateVideoFile, type UploadHandle } from "@/lib/upload";
import { cn } from "@/lib/utils";

type Phase =
  | { kind: "idle" }
  | { kind: "uploading"; loaded: number; total: number }
  | { kind: "finalizing" }
  | { kind: "error"; message: string; retryable: boolean };

function titleFromFile(name: string): string {
  return name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim().slice(0, 200) || "Untitled project";
}

/**
 * Uploads a video directly to private storage and starts processing.
 * Either creates a new project (from the file name or `title`) or uses `projectId`.
 */
export function Uploader({ projectId, title, compact = false }: { projectId?: string; title?: string; compact?: boolean }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const usage = useUsage();
  const system = useSystemStatus();
  const aiAvailable = system.data?.ai_available === true;
  const [shorts, setShorts] = useState<"off" | "30" | "60">("30");
  const inputRef = useRef<HTMLInputElement>(null);
  const handleRef = useRef<UploadHandle | null>(null);
  const projectRef = useRef<string | null>(projectId ?? null);
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);

  const maxBytes = usage.data?.plan.max_upload_bytes ?? null;
  const busy = phase.kind === "uploading" || phase.kind === "finalizing";

  useEffect(() => {
    if (!busy) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);

  const start = useCallback(
    async (f: File) => {
      const invalid = validateVideoFile(f, maxBytes);
      if (invalid) {
        setPhase({ kind: "error", message: invalid, retryable: false });
        return;
      }
      setFile(f);
      setPhase({ kind: "uploading", loaded: 0, total: f.size });
      try {
        if (!projectRef.current) {
          const project = await api<Project>("/api/v1/projects", { body: { title: title?.trim() || titleFromFile(f.name) } });
          projectRef.current = project.id;
        }
        const pid = projectRef.current;
        const target = await api<UploadTarget>(`/api/v1/projects/${pid}/uploads/initiate`, {
          body: { filename: f.name, content_type: contentTypeFor(f), size_bytes: f.size },
        });
        const handle = putToStorage(f, target, (loaded, total) => setPhase({ kind: "uploading", loaded, total }));
        handleRef.current = handle;
        await handle.promise;
        handleRef.current = null;
        setPhase({ kind: "finalizing" });
        try {
          const autoShorts =
            aiAvailable && shorts !== "off"
              ? { target_seconds: Number(shorts), count: 3, captions: true, auto_render: true }
              : undefined;
          await api(`/api/v1/projects/${pid}/uploads/complete`, {
            body: { upload_id: target.upload_id, auto_shorts: autoShorts },
          });
        } catch (err) {
          // The upload is stored and the job saved even if the queue is briefly unavailable.
          if (!(err instanceof ApiError && err.code === "QUEUE_UNAVAILABLE")) throw err;
        }
        await queryClient.invalidateQueries({ queryKey: ["projects"] });
        router.push(`/projects/${pid}`);
      } catch (err) {
        handleRef.current = null;
        if ((err as Error).name === "AbortError") {
          setPhase({ kind: "idle" });
          setFile(null);
          return;
        }
        const retryable = !(err instanceof ApiError) || err.retryable || err.code === "UPLOAD_INCOMPLETE" || err.code === "UPLOAD_MISSING";
        setPhase({ kind: "error", message: errorMessage(err), retryable });
        // Release the server-side upload slot so a retry can start cleanly.
        if (projectRef.current) {
          api(`/api/v1/projects/${projectRef.current}/uploads/abort`, { method: "POST" }).catch(() => {});
        }
      }
    },
    [maxBytes, title, queryClient, router, aiAvailable, shorts],
  );

  const cancel = async () => {
    handleRef.current?.abort();
    if (projectRef.current) {
      await api(`/api/v1/projects/${projectRef.current}/uploads/abort`, { method: "POST" }).catch(() => {});
    }
  };

  const onFiles = (files: FileList | null) => {
    const f = files?.[0];
    if (f && !busy) void start(f);
  };

  return (
    <div className="space-y-3">
      {aiAvailable && !busy && (
        <div className="flex flex-wrap items-center gap-2 text-sm" role="radiogroup" aria-label="AI shorts">
          <span className="inline-flex items-center gap-1.5 font-medium">
            <Sparkles className="size-4 text-accent" aria-hidden /> AI shorts
          </span>
          {(
            [
              ["off", "Off"],
              ["30", "30 seconds"],
              ["60", "1 minute"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={shorts === value}
              onClick={() => setShorts(value)}
              className={cn(
                "rounded-full border px-3 py-1 transition-colors",
                shorts === value ? "border-accent bg-accent-soft text-fg" : "border-border text-muted hover:text-fg",
              )}
            >
              {label}
            </button>
          ))}
          <span className="text-xs text-muted">
            {shorts === "off" ? "Upload only — create clips yourself." : "AI picks the best moments and renders captioned vertical shorts."}
          </span>
        </div>
      )}
      {phase.kind === "uploading" || phase.kind === "finalizing" ? (
        <div className="rounded-[var(--radius-card)] border border-border bg-surface p-5">
          <div className="flex items-center gap-3">
            <FileVideo className="size-8 shrink-0 text-accent" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{file?.name}</p>
              <p className="text-xs text-muted">
                {phase.kind === "uploading"
                  ? `${formatBytes(phase.loaded)} of ${formatBytes(phase.total)} · ${Math.round((phase.loaded / Math.max(phase.total, 1)) * 100)}%`
                  : "Upload complete — verifying file…"}
              </p>
            </div>
            {phase.kind === "uploading" && (
              <Button variant="ghost" size="sm" onClick={cancel}>
                <X /> Cancel
              </Button>
            )}
          </div>
          <Progress
            className="mt-4"
            label="Upload progress"
            value={phase.kind === "uploading" ? phase.loaded / Math.max(phase.total, 1) : 1}
          />
        </div>
      ) : (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            onFiles(e.dataTransfer.files);
          }}
          className={cn(
            "flex flex-col items-center justify-center gap-3 rounded-[var(--radius-card)] border-2 border-dashed text-center transition-colors",
            compact ? "px-4 py-8" : "px-6 py-14",
            dragging ? "border-accent bg-accent-soft" : "border-border bg-surface hover:border-border-strong",
          )}
        >
          <UploadCloud className="size-9 text-accent" aria-hidden />
          <div>
            <p className="font-medium">Drag and drop a video here</p>
            <p className="mt-1 text-sm text-muted">
              MP4, MOV or WebM{maxBytes ? ` · up to ${formatBytes(maxBytes)}` : ""}
              {usage.data ? ` · up to ${Math.round(usage.data.plan.max_video_duration_seconds / 60)} min long` : ""}
            </p>
          </div>
          <Button type="button" variant="secondary" onClick={() => inputRef.current?.click()}>
            Choose file
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT_ATTR}
            className="sr-only"
            aria-label="Choose a video file"
            data-testid="file-input"
            onChange={(e) => {
              onFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
      )}
      {phase.kind === "error" && (
        <Alert
          variant="danger"
          title="Upload failed"
          action={
            phase.retryable && file ? (
              <Button size="sm" variant="secondary" onClick={() => start(file)}>
                <RotateCcw /> Retry
              </Button>
            ) : undefined
          }
        >
          {phase.message}
        </Alert>
      )}
      <p className="text-xs text-muted">Only upload videos you own or have permission to use.</p>
    </div>
  );
}
