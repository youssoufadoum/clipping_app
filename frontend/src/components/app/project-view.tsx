"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Copy, Download, Film, Pencil, Plus, Scissors, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/app/app-shell";
import { ConfirmDialog } from "@/components/app/confirm-dialog";
import { JobStatusPanel } from "@/components/app/job-status";
import { Uploader } from "@/components/app/uploader";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Alert, EmptyState, ErrorState, Progress, Skeleton } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatBytes, formatDateTime, formatDuration, formatTimecode, stageLabel } from "@/lib/format";
import { downloadClip, useDeleteClip, useDuplicateClip, useRenderClip } from "@/lib/mutations";
import { keys, useClips, useJobs, useProject } from "@/lib/queries";
import type { Clip, Project } from "@/lib/types";

const CLIP_READY = new Set(["ready", "completed", "partially_failed", "rendering"]);

function RenameDialog({ project }: { project: Project }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(project.title);
  const rename = useMutation({
    mutationFn: () => api<Project>(`/api/v1/projects/${project.id}`, { method: "PATCH", body: { title } }),
    onSuccess: (p) => {
      qc.setQueryData(keys.project(project.id), p);
      qc.invalidateQueries({ queryKey: ["projects"] });
      setOpen(false);
    },
  });
  return (
    <Dialog open={open} onOpenChange={(o) => (setOpen(o), setTitle(project.title))}>
      <DialogTrigger asChild>
        <Button variant="secondary" size="sm">
          <Pencil /> Rename
        </Button>
      </DialogTrigger>
      <DialogContent title="Rename project">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) rename.mutate();
          }}
        >
          <Input aria-label="Project title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} autoFocus />
          {rename.isError && <Alert variant="danger">{errorMessage(rename.error)}</Alert>}
          <div className="flex justify-end">
            <Button type="submit" loading={rename.isPending} disabled={!title.trim()}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SourceDetails({ project }: { project: Project }) {
  const m = project.source_metadata;
  const rows: [string, string][] = [
    ["File", project.source_filename ?? "—"],
    ["Duration", formatDuration(project.source_duration_seconds)],
    ["Resolution", project.source_width ? `${project.source_width} × ${project.source_height}` : "—"],
    ["Frame rate", project.source_fps ? `${project.source_fps} fps` : "—"],
    ["Video codec", m.video_codec ?? "—"],
    ["Audio", m.has_audio === false ? "No audio track" : (m.audio_codec ?? "—")],
    ["Size", formatBytes(project.source_size_bytes)],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Source video</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {project.thumbnail_url && (
          // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
          <img src={project.thumbnail_url} alt="Source video thumbnail" className="aspect-video w-full rounded-lg object-cover" />
        )}
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd className="truncate text-right" title={v}>
                {v}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function ClipRow({ clip, projectId }: { clip: Clip; projectId: string }) {
  const toast = useToast();
  const render = useRenderClip(projectId);
  const duplicate = useDuplicateClip(projectId);
  const remove = useDeleteClip(projectId);
  const [downloading, setDownloading] = useState(false);
  const working = clip.status === "queued" || clip.status === "rendering";
  const job = clip.latest_job;
  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex h-16 w-12 shrink-0 items-center justify-center overflow-hidden rounded bg-surface-2">
          {clip.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
            <img src={clip.thumbnail_url} alt="" className="h-full w-full object-cover" />
          ) : (
            <Film className="size-5 text-muted" aria-hidden />
          )}
        </div>
        <div className="min-w-0 space-y-1">
          <Link href={`/projects/${projectId}/clips/${clip.id}`} className="block truncate font-medium hover:text-accent">
            {clip.title}
          </Link>
          <p className="text-xs text-muted">
            {formatTimecode(clip.start_seconds)} – {formatTimecode(clip.end_seconds)} · {formatDuration(clip.duration_seconds)} ·{" "}
            {clip.render_settings.aspect_ratio}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={clip.status} />
            {clip.status === "rendered" && !clip.render_is_current && <span className="text-xs text-warning">Edited since last render</span>}
            {clip.status === "failed" && job?.safe_error_message && <span className="text-xs text-danger">{job.safe_error_message}</span>}
          </div>
          {working && job && (
            <div className="flex items-center gap-2 pt-1">
              <Progress value={job.progress} className="w-40" label={`Render progress for ${clip.title}`} />
              <span className="text-xs text-muted">{stageLabel(job.stage)}</span>
            </div>
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Button asChild size="sm" variant="secondary">
          <Link href={`/projects/${projectId}/clips/${clip.id}`}>
            <Scissors /> Edit
          </Link>
        </Button>
        <Button size="sm" variant="secondary" disabled={working} loading={render.isPending} onClick={() => render.mutate(clip.id)}>
          {clip.status === "rendered" ? "Re-render" : "Render"}
        </Button>
        {clip.status === "rendered" && (
          <Button
            size="sm"
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
            <Download /> Download
          </Button>
        )}
        <Button size="icon" variant="ghost" aria-label={`Duplicate ${clip.title}`} onClick={() => duplicate.mutate(clip.id)}>
          <Copy />
        </Button>
        <ConfirmDialog
          title="Delete clip?"
          description="The clip and its exported files will be permanently deleted."
          onConfirm={() => remove.mutateAsync(clip.id)}
          trigger={
            <Button size="icon" variant="ghost" aria-label={`Delete ${clip.title}`}>
              <Trash2 />
            </Button>
          }
        />
      </div>
    </li>
  );
}

function ClipsSection({ project }: { project: Project }) {
  const router = useRouter();
  const toast = useToast();
  const clips = useClips(project.id);
  const create = useMutation({
    mutationFn: () => {
      const duration = project.source_duration_seconds ?? 0;
      return api<Clip>(`/api/v1/projects/${project.id}/clips`, {
        body: {
          title: `Clip ${(clips.data?.length ?? 0) + 1}`,
          start_seconds: 0,
          end_seconds: Math.min(30, Math.floor(duration * 10) / 10),
          render_settings: { aspect_ratio: "9:16", fit: "crop", crop_x: 0.5, crop_y: 0.5, pad_color: "black", normalize_audio: false },
        },
      });
    },
    onSuccess: (clip) => router.push(`/projects/${project.id}/clips/${clip.id}`),
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Clips</CardTitle>
        <Button size="sm" onClick={() => create.mutate()} loading={create.isPending}>
          <Plus /> New clip
        </Button>
      </CardHeader>
      <CardContent>
        {clips.isPending ? (
          <Skeleton className="h-24" />
        ) : clips.isError ? (
          <ErrorState message={errorMessage(clips.error)} onRetry={() => clips.refetch()} />
        ) : clips.data.length === 0 ? (
          <EmptyState
            icon={<Scissors />}
            title="No clips yet"
            description="Create a clip, mark its start and end on the timeline, then render it for your platform."
            action={
              <Button onClick={() => create.mutate()} loading={create.isPending}>
                <Plus /> Create your first clip
              </Button>
            }
          />
        ) : (
          <ul className="space-y-2">
            {clips.data.map((c) => (
              <ClipRow key={c.id} clip={c} projectId={project.id} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function JobHistory({ projectId }: { projectId: string }) {
  const jobs = useJobs(projectId);
  if (!jobs.data?.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Job history</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border text-sm">
          {jobs.data.map((j) => (
            <li key={j.id} className="flex items-center justify-between gap-3 py-2">
              <span className="truncate">
                {j.job_type === "inspect_media" ? "Video inspection" : j.job_type === "render_clip" ? "Clip render" : j.job_type}
                <span className="block text-xs text-muted">{formatDateTime(j.created_at)}{j.error_code ? ` · ${j.error_code}` : ""}</span>
              </span>
              <StatusBadge status={j.status} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function ProjectView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const project = useProject(id);
  const latestJobKey = project.data?.latest_job ? `${project.data.latest_job.id}:${project.data.latest_job.status}` : "";
  // Refresh job history whenever the latest job changes state.
  useEffect(() => {
    if (latestJobKey) void qc.invalidateQueries({ queryKey: keys.jobs(id) });
  }, [latestJobKey, id, qc]);

  const archive = useMutation({
    mutationFn: (archived: boolean) => api<Project>(`/api/v1/projects/${id}`, { method: "PATCH", body: { archived } }),
    onSuccess: (p) => {
      qc.setQueryData(keys.project(id), p);
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast(p.status === "archived" ? "Project archived" : "Project restored");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (project.isPending) {
    return (
      <div className="space-y-4 p-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (project.isError) {
    const notFound = project.error instanceof ApiError && project.error.status === 404;
    return (
      <div className="p-8">
        <ErrorState title={notFound ? "Project not found" : "Project could not be loaded"} message={errorMessage(project.error)} onRetry={notFound ? undefined : () => project.refetch()} />
      </div>
    );
  }

  const p = project.data;
  const job = p.latest_job;
  const inspectJob = job?.job_type === "inspect_media" ? job : null;

  return (
    <>
      <PageHeader
        title={p.title}
        description={
          <span className="inline-flex items-center gap-2">
            <StatusBadge status={p.status} /> Created {formatDateTime(p.created_at)}
          </span>
        }
        actions={
          <>
            <RenameDialog project={p} />
            {p.status === "archived" ? (
              <Button variant="secondary" size="sm" onClick={() => archive.mutate(false)} loading={archive.isPending}>
                <ArchiveRestore /> Restore
              </Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={() => archive.mutate(true)} loading={archive.isPending}>
                <Archive /> Archive
              </Button>
            )}
            <ConfirmDialog
              title="Delete project?"
              description="This permanently deletes the source video, all clips and all exports."
              confirmLabel="Delete project"
              onConfirm={async () => {
                await api(`/api/v1/projects/${id}`, { method: "DELETE" });
                qc.invalidateQueries({ queryKey: ["projects"] });
                toast("Project deleted");
                router.replace("/dashboard");
              }}
              trigger={
                <Button variant="secondary" size="sm">
                  <Trash2 /> Delete
                </Button>
              }
            />
          </>
        }
      />
      <div className="grid gap-6 px-4 py-6 sm:px-8 xl:grid-cols-[1fr_340px]">
        <div className="min-w-0 space-y-6">
          {(p.status === "draft" || p.status === "uploading") && (
            <Card>
              <CardHeader>
                <CardTitle>Upload a video</CardTitle>
              </CardHeader>
              <CardContent>
                {p.status === "uploading" && (
                  <Alert variant="info" className="mb-4">
                    An upload was started but not finished. Choose the file again to restart it.
                  </Alert>
                )}
                <Uploader projectId={p.id} />
              </CardContent>
            </Card>
          )}
          {inspectJob && (inspectJob.status !== "succeeded" || p.status === "failed") && (
            <JobStatusPanel job={inspectJob} label="Video processing" invalidate={[keys.project(id), keys.jobs(id)]} />
          )}
          {CLIP_READY.has(p.status) && <ClipsSection project={p} />}
          {p.status === "archived" && (
            <Alert variant="info" title="This project is archived">
              Restore it to create or render clips.
            </Alert>
          )}
        </div>
        <aside className="space-y-6">
          {p.source_duration_seconds != null && <SourceDetails project={p} />}
          <JobHistory projectId={p.id} />
        </aside>
      </div>
    </>
  );
}
