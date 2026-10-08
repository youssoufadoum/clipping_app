"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Alert, Progress } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { stageLabel } from "@/lib/format";
import type { Job } from "@/lib/types";

/** Shows a job's real stage and progress as reported by the worker, with cancel/retry. */
export function JobStatusPanel({ job, invalidate, label }: { job: Job; invalidate: readonly (readonly unknown[])[]; label: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const refresh = () => invalidate.forEach((queryKey) => qc.invalidateQueries({ queryKey }));
  const cancel = useMutation({
    mutationFn: () => api<Job>(`/api/v1/jobs/${job.id}/cancel`, { method: "POST" }),
    onSuccess: refresh,
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const retry = useMutation({
    mutationFn: () => api<Job>(`/api/v1/jobs/${job.id}/retry`, { method: "POST" }),
    onSuccess: () => {
      toast("Retry started");
      refresh();
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (job.status === "queued" || job.status === "running") {
    return (
      <div className="space-y-2 rounded-lg border border-border bg-surface-2 p-4" aria-live="polite">
        <div className="flex items-center justify-between gap-3 text-sm">
          <span>
            {label}: <span className="text-muted">{job.cancel_requested ? "Cancelling…" : stageLabel(job.stage) || "Queued"}</span>
            {job.attempt_count > 1 && <span className="text-muted"> · attempt {job.attempt_count} of {job.max_attempts}</span>}
          </span>
          {!job.cancel_requested && (
            <Button size="sm" variant="ghost" loading={cancel.isPending} onClick={() => cancel.mutate()}>
              <X /> Cancel
            </Button>
          )}
        </div>
        <Progress value={job.progress} label={`${label} progress`} />
      </div>
    );
  }
  if (job.status === "failed" || job.status === "cancelled") {
    return (
      <Alert
        variant={job.status === "failed" ? "danger" : "warning"}
        title={job.status === "failed" ? `${label} failed` : `${label} cancelled`}
        action={
          <Button size="sm" variant="secondary" loading={retry.isPending} onClick={() => retry.mutate()}>
            <RotateCcw /> Retry
          </Button>
        }
      >
        {job.safe_error_message ?? "The job was stopped before it finished."}
        {job.error_code && <span className="mt-1 block font-mono text-xs opacity-70">Code {job.error_code} · Job {job.id.slice(0, 8)}</span>}
      </Alert>
    );
  }
  return null;
}
