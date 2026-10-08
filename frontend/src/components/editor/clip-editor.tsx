"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Pause, Play, Redo2, Repeat, Save, Undo2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { JobStatusPanel } from "@/components/app/job-status";
import { Timeline } from "@/components/editor/timeline";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Alert, ErrorState, Skeleton, Spinner } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { cropBox, round1, sameState, validateRange, type EditorState } from "@/lib/editor";
import { formatDuration, formatTimecode, parseTimecode } from "@/lib/format";
import { downloadClip } from "@/lib/mutations";
import { keys, useClip, useProject } from "@/lib/queries";
import type { AspectRatio, Clip, Job, Project, SignedUrl } from "@/lib/types";
import { cn } from "@/lib/utils";

const RATIO_OPTIONS: { value: AspectRatio; label: string; hint: string }[] = [
  { value: "9:16", label: "9:16", hint: "TikTok, Shorts, Reels" },
  { value: "1:1", label: "1:1", hint: "Feed posts" },
  { value: "16:9", label: "16:9", hint: "YouTube, LinkedIn" },
  { value: "original", label: "Original", hint: "Keep source framing" },
];

function toState(clip: Clip): EditorState {
  return { title: clip.title, start: clip.start_seconds, end: clip.end_seconds, render: { ...clip.render_settings } };
}

interface HistoryState {
  past: EditorState[];
  present: EditorState; // last committed state
  future: EditorState[];
  live: EditorState; // includes in-progress changes (e.g. while dragging)
}

type HistoryAction =
  | { type: "update"; patch: Partial<EditorState> }
  | { type: "commit" }
  | { type: "undo" }
  | { type: "redo" }
  | { type: "reset"; state: EditorState };

export function historyReducer(h: HistoryState, a: HistoryAction): HistoryState {
  switch (a.type) {
    case "update":
      return { ...h, live: { ...h.live, ...a.patch } };
    case "commit":
      if (sameState(h.live, h.present)) return h;
      return { past: [...h.past, h.present].slice(-100), present: h.live, future: [], live: h.live };
    case "undo": {
      const base = sameState(h.live, h.present) ? h : historyReducer(h, { type: "commit" });
      const prev = base.past[base.past.length - 1];
      if (!prev) return base;
      return { past: base.past.slice(0, -1), present: prev, future: [base.present, ...base.future], live: prev };
    }
    case "redo": {
      const next = h.future[0];
      if (!next) return h;
      return { past: [...h.past, h.present], present: next, future: h.future.slice(1), live: next };
    }
    case "reset":
      return { past: [], present: a.state, future: [], live: a.state };
  }
}

/** Undo/redo history over committed editor states. */
function useHistory(initial: EditorState) {
  const [h, dispatch] = useReducer(historyReducer, { past: [], present: initial, future: [], live: initial });
  const update = useCallback((patch: Partial<EditorState>) => dispatch({ type: "update", patch }), []);
  const commit = useCallback(() => dispatch({ type: "commit" }), []);
  const set = useCallback((patch: Partial<EditorState>) => {
    dispatch({ type: "update", patch });
    dispatch({ type: "commit" });
  }, []);
  const undo = useCallback(() => dispatch({ type: "undo" }), []);
  const redo = useCallback(() => dispatch({ type: "redo" }), []);
  const reset = useCallback((state: EditorState) => dispatch({ type: "reset", state }), []);
  return { state: h.live, update, commit, set, undo, redo, reset, canUndo: h.past.length > 0 || !sameState(h.live, h.present), canRedo: h.future.length > 0 };
}

function TimeField({ id, label, value, onCommit }: { id: string; label: string; value: number; onCommit: (v: number) => void }) {
  // Keyed by value in the parent, so external changes remount with fresh text.
  const [text, setText] = useState(formatTimecode(value));
  const [invalid, setInvalid] = useState(false);
  const apply = () => {
    const parsed = parseTimecode(text);
    if (parsed == null) {
      setInvalid(true);
      return;
    }
    onCommit(round1(parsed));
  };
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs text-muted">
        {label}
      </Label>
      <Input
        id={id}
        value={text}
        aria-invalid={invalid}
        className="h-9 font-mono"
        onChange={(e) => setText(e.target.value)}
        onBlur={apply}
        onKeyDown={(e) => e.key === "Enter" && apply()}
      />
    </div>
  );
}

function RenderedPreview({ clip }: { clip: Clip }) {
  const [playbackFailed, setPlaybackFailed] = useState(false);
  const preview = useQuery({
    queryKey: ["clip-preview", clip.id, clip.latest_job?.id],
    queryFn: () => api<SignedUrl>(`/api/v1/clips/${clip.id}/download?inline=true`),
    enabled: clip.status === "rendered",
    staleTime: 5 * 60_000,
  });
  if (clip.status !== "rendered") return null;
  if (preview.isPending) return <Skeleton className="aspect-[9/16] w-full max-w-[220px]" />;
  if (preview.isError) return <ErrorState message={errorMessage(preview.error)} onRetry={() => preview.refetch()} />;
  if (playbackFailed) {
    return (
      <Alert variant="info" title="Preview unavailable in this browser">
        The export is ready — download it to watch.
      </Alert>
    );
  }
  return (
    <video
      onError={() => setPlaybackFailed(true)}
      key={preview.data.url}
      src={preview.data.url}
      controls
      playsInline
      preload="metadata"
      className="max-h-80 w-full rounded-lg bg-black object-contain"
      aria-label="Rendered clip preview"
    />
  );
}

function EditorBody({ project, clip }: { project: Project; clip: Clip }) {
  const qc = useQueryClient();
  const toast = useToast();
  const history = useHistory(toState(clip));
  const { state, update, commit, set, undo, redo, reset } = history;
  const [saved, setSaved] = useState<EditorState>(() => toState(clip));
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(clip.start_seconds);
  const [loopClip, setLoopClip] = useState(true);
  const [videoError, setVideoError] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const duration = project.source_duration_seconds ?? 0;
  const sw = project.source_width ?? 16;
  const sh = project.source_height ?? 9;
  const dirty = !sameState(state, saved);
  const rangeError = validateRange(state.start, state.end, duration);
  const titleError = state.title.trim() ? null : "Give the clip a title.";
  const box = cropBox(sw, sh, state.render.aspect_ratio, state.render.fit, state.render.crop_x, state.render.crop_y);
  const rendering = clip.status === "queued" || clip.status === "rendering";

  const source = useQuery({
    queryKey: ["source-url", project.id],
    queryFn: () => api<{ url: string; expires_in: number }>(`/api/v1/projects/${project.id}/source-url`),
    staleTime: 10 * 60_000,
  });

  // Adopt server-side changes (e.g. saved in another tab) when there are no local edits.
  const serverState = useMemo(() => toState(clip), [clip]);
  const [prevServer, setPrevServer] = useState(serverState);
  if (!sameState(prevServer, serverState)) {
    setPrevServer(serverState);
    if (!dirty && !sameState(serverState, saved)) {
      setSaved(serverState);
      reset(serverState);
    }
  }

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = useMutation({
    mutationFn: (s: EditorState) =>
      api<Clip>(`/api/v1/clips/${clip.id}`, {
        method: "PATCH",
        body: { title: s.title.trim(), start_seconds: s.start, end_seconds: s.end, render_settings: s.render },
      }),
    onSuccess: (updated) => {
      qc.setQueryData(keys.clip(clip.id), updated);
      qc.invalidateQueries({ queryKey: keys.clips(project.id) });
      setSaved(toState(updated));
    },
  });

  const render = useMutation({
    mutationFn: async () => {
      if (dirty) await save.mutateAsync(state);
      return api<Job>(`/api/v1/clips/${clip.id}/render`, { method: "POST" });
    },
    onSuccess: () => {
      toast("Render started — you can leave this page.");
      qc.invalidateQueries({ queryKey: keys.clip(clip.id) });
      qc.invalidateQueries({ queryKey: keys.clips(project.id) });
      qc.invalidateQueries({ queryKey: keys.usage });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const seek = useCallback((t: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.min(Math.max(t, 0), duration);
    setCurrent(v.currentTime);
  }, [duration]);

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      if (loopClip && (v.currentTime < state.start || v.currentTime >= state.end - 0.05)) v.currentTime = state.start;
      void v.play();
    } else {
      v.pause();
    }
  }, [loopClip, state.start, state.end]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest("input, textarea, select, [role=slider]")) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (dirty && !rangeError && !titleError) save.mutate(state);
      } else if (e.key === " " && !target.closest("button")) {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo, togglePlay, dirty, rangeError, titleError, save, state]);

  const setRange = (start: number, end: number) => set({ start: round1(start), end: round1(end) });
  const renderSettings = (patch: Partial<EditorState["render"]>) => set({ render: { ...state.render, ...patch } });

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] flex-col lg:min-h-screen">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 sm:px-6">
        <Button asChild variant="ghost" size="sm">
          <Link href={`/projects/${project.id}`}>
            <ArrowLeft /> <span className="hidden sm:inline">{project.title}</span>
            <span className="sm:hidden">Back</span>
          </Link>
        </Button>
        <div className="flex items-center gap-2">
          <StatusBadge status={clip.status} />
          {clip.status === "rendered" && !clip.render_is_current && <span className="text-xs text-warning">Edited since last render</span>}
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <Button variant="ghost" size="icon" aria-label="Undo" title="Undo (Ctrl+Z)" disabled={!history.canUndo} onClick={undo}>
            <Undo2 />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Redo" title="Redo (Ctrl+Shift+Z)" disabled={!history.canRedo} onClick={redo}>
            <Redo2 />
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={!dirty || !!rangeError || !!titleError}
            loading={save.isPending}
            onClick={() => save.mutate(state, { onSuccess: () => toast("Changes saved") })}
          >
            <Save /> {dirty ? "Save" : "Saved"}
          </Button>
          <Button size="sm" disabled={rendering || !!rangeError || !!titleError} loading={render.isPending} onClick={() => render.mutate()}>
            {clip.status === "rendered" ? "Re-render" : "Render"}
          </Button>
        </div>
      </div>

      {save.isError && (
        <div className="px-4 pt-3 sm:px-6">
          <Alert variant="danger" title="Changes not saved">
            {errorMessage(save.error)}
          </Alert>
        </div>
      )}

      <div className="grid flex-1 gap-6 p-4 sm:p-6 xl:grid-cols-[1fr_340px]">
        <div className="min-w-0 space-y-4">
          <div className="flex justify-center rounded-xl bg-black/60 p-2 sm:p-4">
            <div className="relative w-full max-w-4xl overflow-hidden rounded-lg bg-black" style={{ aspectRatio: `${sw} / ${sh}`, maxHeight: "60vh" }}>
              {source.isPending ? (
                <div className="flex h-full items-center justify-center">
                  <Spinner label="Loading source video" />
                </div>
              ) : source.isError || videoError ? (
                <div className="flex h-full items-center justify-center p-6">
                  <ErrorState
                    title="Preview unavailable"
                    message={
                      source.isError
                        ? errorMessage(source.error)
                        : "This browser couldn't play the source video — its format may not be supported, or the link expired. You can still set start and end times below."
                    }
                    onRetry={() => {
                      setVideoError(false);
                      void source.refetch();
                    }}
                  />
                </div>
              ) : (
                <>
                  <video
                    ref={videoRef}
                    src={source.data.url}
                    className="absolute inset-0 h-full w-full"
                    playsInline
                    preload="metadata"
                    onLoadedMetadata={(e) => (e.currentTarget.currentTime = state.start)}
                    onTimeUpdate={(e) => {
                      const v = e.currentTarget;
                      setCurrent(v.currentTime);
                      if (loopClip && !v.paused && v.currentTime >= state.end) {
                        v.currentTime = state.start;
                      }
                    }}
                    onPlay={() => setPlaying(true)}
                    onPause={() => setPlaying(false)}
                    onError={() => setVideoError(true)}
                    onClick={togglePlay}
                  />
                  {box.axis && (
                    <div className="pointer-events-none absolute inset-0" aria-hidden>
                      <div
                        className="absolute border-2 border-accent shadow-[0_0_0_9999px_rgba(0,0,0,0.55)]"
                        style={{ left: `${box.left * 100}%`, top: `${box.top * 100}%`, width: `${box.width * 100}%`, height: `${box.height * 100}%` }}
                      />
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="space-y-3 rounded-xl border border-border bg-surface p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" size="icon" aria-label={playing ? "Pause" : "Play"} onClick={togglePlay}>
                {playing ? <Pause /> : <Play />}
              </Button>
              <span className="font-mono text-sm tabular-nums">{formatTimecode(current)}</span>
              <Button
                variant={loopClip ? "secondary" : "ghost"}
                size="sm"
                aria-pressed={loopClip}
                onClick={() => setLoopClip((l) => !l)}
                title="Loop playback inside the clip"
              >
                <Repeat /> Loop clip
              </Button>
              <div className="ml-auto flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setRange(Math.min(current, state.end - 1), state.end)}>
                  Set start
                </Button>
                <Button variant="outline" size="sm" onClick={() => setRange(state.start, Math.max(current, state.start + 1))}>
                  Set end
                </Button>
              </div>
            </div>
            <Timeline
              duration={duration}
              start={state.start}
              end={state.end}
              current={current}
              onChange={(s, e) => update({ start: round1(s), end: round1(e) })}
              onCommit={commit}
              onSeek={seek}
            />
            <div className="grid grid-cols-3 gap-3">
              <TimeField key={`s${state.start}`} id="start" label="Start" value={state.start} onCommit={(v) => setRange(v, state.end)} />
              <TimeField key={`e${state.end}`} id="end" label="End" value={state.end} onCommit={(v) => setRange(state.start, v)} />
              <div className="space-y-1">
                <span className="text-xs text-muted">Length</span>
                <p className="flex h-9 items-center font-mono text-sm">{formatDuration(state.end - state.start)}</p>
              </div>
            </div>
            {rangeError && <p role="alert" className="text-sm text-danger">{rangeError}</p>}
          </div>
        </div>

        <aside className="space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="clip-title">Title</Label>
            <Input
              id="clip-title"
              value={state.title}
              maxLength={200}
              aria-invalid={!!titleError}
              onChange={(e) => update({ title: e.target.value })}
              onBlur={commit}
            />
            {titleError && <p className="text-xs text-danger">{titleError}</p>}
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Format</legend>
            <div className="grid grid-cols-2 gap-2">
              {RATIO_OPTIONS.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  aria-pressed={state.render.aspect_ratio === r.value}
                  onClick={() => renderSettings({ aspect_ratio: r.value })}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-left transition-colors",
                    state.render.aspect_ratio === r.value ? "border-accent bg-accent-soft" : "border-border hover:border-border-strong",
                  )}
                >
                  <span className="block text-sm font-medium">{r.label}</span>
                  <span className="block text-[11px] text-muted">{r.hint}</span>
                </button>
              ))}
            </div>
          </fieldset>

          {state.render.aspect_ratio !== "original" && (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Framing</legend>
              <div className="grid grid-cols-2 gap-2">
                {(["crop", "pad"] as const).map((f) => (
                  <button
                    key={f}
                    type="button"
                    aria-pressed={state.render.fit === f}
                    onClick={() => renderSettings({ fit: f })}
                    className={cn(
                      "rounded-lg border px-3 py-2 text-sm transition-colors",
                      state.render.fit === f ? "border-accent bg-accent-soft" : "border-border hover:border-border-strong",
                    )}
                  >
                    {f === "crop" ? "Fill (crop)" : "Fit (pad)"}
                  </button>
                ))}
              </div>
              {box.axis && (
                <div className="space-y-1.5 pt-1">
                  <Label htmlFor="crop-pos" className="text-xs text-muted">
                    {box.axis === "x" ? "Horizontal position" : "Vertical position"}
                  </Label>
                  <input
                    id="crop-pos"
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={box.axis === "x" ? state.render.crop_x : state.render.crop_y}
                    onChange={(e) =>
                      update({ render: { ...state.render, [box.axis === "x" ? "crop_x" : "crop_y"]: Number(e.target.value) } })
                    }
                    onPointerUp={commit}
                    onKeyUp={commit}
                    className="w-full accent-[var(--accent)]"
                  />
                  <p className="text-[11px] text-muted">Drag to keep your subject inside the highlighted frame.</p>
                </div>
              )}
              {state.render.fit === "pad" && (
                <div className="space-y-1.5 pt-1">
                  <span className="text-xs text-muted">Padding color</span>
                  <div className="flex gap-2">
                    {(["black", "white", "0x111827"] as const).map((c) => (
                      <button
                        key={c}
                        type="button"
                        aria-label={`Padding ${c === "0x111827" ? "charcoal" : c}`}
                        aria-pressed={state.render.pad_color === c}
                        onClick={() => renderSettings({ pad_color: c })}
                        className={cn(
                          "size-8 rounded-md border-2",
                          state.render.pad_color === c ? "border-accent" : "border-border",
                          c === "black" ? "bg-black" : c === "white" ? "bg-white" : "bg-[#111827]",
                        )}
                      />
                    ))}
                  </div>
                </div>
              )}
            </fieldset>
          )}

          <label className="flex items-start gap-3 rounded-lg border border-border p-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 accent-[var(--accent)]"
              checked={state.render.normalize_audio}
              onChange={(e) => renderSettings({ normalize_audio: e.target.checked })}
            />
            <span>
              Normalize loudness
              <span className="block text-xs text-muted">Evens out volume to a consistent level (EBU R128).</span>
            </span>
          </label>

          <div className="space-y-3 border-t border-border pt-5">
            <h2 className="text-sm font-medium">Export</h2>
            {clip.latest_job && clip.latest_job.job_type === "render_clip" && (
              <JobStatusPanel job={clip.latest_job} label="Render" invalidate={[keys.clip(clip.id), keys.clips(project.id)]} />
            )}
            {clip.status === "rendered" && (
              <>
                <RenderedPreview clip={clip} />
                <Button
                  className="w-full"
                  loading={downloading}
                  onClick={async () => {
                    setDownloading(true);
                    try {
                      await downloadClip(clip.id);
                    } catch (e) {
                      toast(errorMessage(e), "error");
                    } finally {
                      setDownloading(false);
                    }
                  }}
                >
                  <Download /> Download MP4
                </Button>
              </>
            )}
            {clip.status === "draft" && !clip.latest_job && (
              <p className="text-sm text-muted">Render the clip to create a downloadable MP4.</p>
            )}
          </div>
          <p className="text-[11px] text-muted">Shortcuts: Space play/pause · Ctrl+S save · Ctrl+Z undo · arrows nudge selected handle.</p>
        </aside>
      </div>
    </div>
  );
}

export function ClipEditor() {
  const { id, clipId } = useParams<{ id: string; clipId: string }>();
  const project = useProject(id);
  const clip = useClip(clipId);

  if (project.isPending || clip.isPending) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="aspect-video w-full max-w-4xl" />
      </div>
    );
  }
  if (project.isError || clip.isError) {
    return (
      <div className="p-6">
        <ErrorState title="Clip could not be loaded" message={errorMessage(project.error ?? clip.error)} />
      </div>
    );
  }
  if (clip.data.project_id !== project.data.id) {
    return (
      <div className="p-6">
        <ErrorState title="Clip not found" message="This clip doesn't belong to the selected project." />
      </div>
    );
  }
  return <EditorBody key={clip.data.id} project={project.data} clip={clip.data} />;
}
