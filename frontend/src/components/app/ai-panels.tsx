"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, Sparkles } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Skeleton } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatTimecode } from "@/lib/format";
import { keys, useTranscript } from "@/lib/queries";
import type { Job, Project, Transcript } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Ask the AI to find the best moments and turn them into shorts. */
export function AiShortsCard({ project, aiAvailable }: { project: Project; aiAvailable: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [target, setTarget] = useState<30 | 60>(30);
  const [count, setCount] = useState(3);
  const [captions, setCaptions] = useState(true);
  const [autoRender, setAutoRender] = useState(true);
  const [instructions, setInstructions] = useState("");

  const run = useMutation({
    mutationFn: () =>
      api<Job>(`/api/v1/projects/${project.id}/analyze`, {
        body: { target_seconds: target, count, captions, auto_render: autoRender, instructions: instructions.trim() || null },
      }),
    onSuccess: () => {
      toast("AI is finding your best moments");
      qc.invalidateQueries({ queryKey: keys.project(project.id) });
      qc.invalidateQueries({ queryKey: keys.usage });
    },
  });

  if (!aiAvailable) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-accent" aria-hidden /> AI shorts
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Alert variant="info" title="AI isn't configured on this server">
            Add a GEMINI_API_KEY to the backend to let AI find the best 30-second or 1-minute moments automatically.
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const busy = project.status === "transcribing" || project.status === "analyzing" || project.status === "generating";
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-4 text-accent" aria-hidden /> Make shorts with AI
        </CardTitle>
        <CardDescription>AI transcribes the video, picks self-contained moments, and renders vertical clips with captions.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-4">
          <fieldset className="space-y-1.5">
            <legend className="text-xs text-muted">Length</legend>
            <div className="flex gap-2">
              {([30, 60] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={target === t}
                  onClick={() => setTarget(t)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-sm",
                    target === t ? "border-accent bg-accent-soft" : "border-border hover:border-border-strong",
                  )}
                >
                  {t === 30 ? "30 seconds" : "1 minute"}
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset className="space-y-1.5">
            <legend className="text-xs text-muted">How many</legend>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  aria-pressed={count === n}
                  onClick={() => setCount(n)}
                  className={cn("size-9 rounded-lg border text-sm", count === n ? "border-accent bg-accent-soft" : "border-border")}
                >
                  {n}
                </button>
              ))}
            </div>
          </fieldset>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" className="accent-[var(--accent)]" checked={captions} onChange={(e) => setCaptions(e.target.checked)} />
            Burn in captions
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="accent-[var(--accent)]" checked={autoRender} onChange={(e) => setAutoRender(e.target.checked)} />
            Render automatically
          </label>
        </div>
        <Input
          aria-label="Optional instructions for the AI"
          placeholder="Optional: e.g. focus on the marketing tips"
          maxLength={500}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
        {run.isError && (
          <Alert variant="danger">
            {errorMessage(run.error)}
            {run.error instanceof ApiError && run.error.code === "QUOTA_EXCEEDED" && " Check your Usage page."}
          </Alert>
        )}
        <Button onClick={() => run.mutate()} loading={run.isPending} disabled={busy || project.status !== "ready"}>
          <Sparkles /> {busy ? "AI is working…" : "Find viral moments"}
        </Button>
        <p className="text-xs text-muted">
          Scores are AI estimates to help you choose — not a guarantee of views. Uses AI minutes once per video; re-running reuses the transcript.
        </p>
      </CardContent>
    </Card>
  );
}

/** Read and correct the AI transcript. Corrections flow into captions on the next render. */
export function TranscriptPanel({ projectId, enabled }: { projectId: string; enabled: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const transcript = useTranscript(projectId, enabled);
  const [open, setOpen] = useState(false);
  const [edits, setEdits] = useState<Record<number, string>>({});

  const save = useMutation({
    mutationFn: () =>
      api<Transcript>(`/api/v1/projects/${projectId}/transcript`, {
        method: "PATCH",
        body: { segments: Object.entries(edits).map(([index, text]) => ({ index: Number(index), text })) },
      }),
    onSuccess: (t) => {
      qc.setQueryData(keys.transcript(projectId), t);
      setEdits({});
      toast("Transcript saved — re-render clips to update their captions");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (!enabled || transcript.isError) return null;
  if (transcript.isPending) return <Skeleton className="h-16" />;
  const t = transcript.data;
  const dirty = Object.keys(edits).length > 0;
  const invalid = Object.values(edits).some((v) => !v.trim());

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <FileText className="size-4" aria-hidden /> Transcript
          </CardTitle>
          <CardDescription>
            {t.segments.length} phrases{t.language ? ` · ${t.language.toUpperCase()}` : ""} · timing is per phrase, not per word
          </CardDescription>
        </div>
        <Button variant="secondary" size="sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "Hide" : "Review & edit"}
        </Button>
      </CardHeader>
      {open && (
        <CardContent className="space-y-3">
          <ol className="max-h-96 space-y-1.5 overflow-y-auto pr-1">
            {t.segments.map((s, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-2.5 w-14 shrink-0 font-mono text-[11px] text-muted">{formatTimecode(s.start)}</span>
                <Input
                  aria-label={`Phrase at ${formatTimecode(s.start)}`}
                  value={edits[i] ?? s.text}
                  maxLength={1000}
                  onChange={(e) => {
                    const value = e.target.value;
                    setEdits((prev) => {
                      const next = { ...prev };
                      if (value === s.text) delete next[i];
                      else next[i] = value;
                      return next;
                    });
                  }}
                  className={cn("h-9", edits[i] !== undefined && "border-accent")}
                />
              </li>
            ))}
          </ol>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" disabled={!dirty} onClick={() => setEdits({})}>
              Discard
            </Button>
            <Button size="sm" disabled={!dirty || invalid} loading={save.isPending} onClick={() => save.mutate()}>
              Save transcript
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
