import { Film } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/status-badge";
import { formatDate, formatDuration } from "@/lib/format";
import type { Project } from "@/lib/types";

export function ProjectCard({ project }: { project: Project }) {
  const job = project.latest_job;
  const working = job && (job.status === "queued" || job.status === "running");
  return (
    <Link
      href={`/projects/${project.id}`}
      className="group flex flex-col overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface transition-colors hover:border-border-strong"
    >
      <div className="relative aspect-video bg-surface-2">
        {project.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
          <img src={project.thumbnail_url} alt="" className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div className="flex h-full items-center justify-center text-muted">
            <Film className="size-8" aria-hidden />
          </div>
        )}
        {project.source_duration_seconds != null && (
          <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-xs text-white">
            {formatDuration(project.source_duration_seconds)}
          </span>
        )}
        {working && (
          <div className="absolute inset-x-0 bottom-0 h-1 bg-black/40">
            <div className="h-full bg-accent transition-[width]" style={{ width: `${Math.round(job.progress * 100)}%` }} />
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-2 font-medium group-hover:text-accent">{project.title}</h3>
          <StatusBadge status={project.status} />
        </div>
        <p className="mt-auto text-xs text-muted">
          {project.clip_count} {project.clip_count === 1 ? "clip" : "clips"} · {formatDate(project.created_at)}
        </p>
      </div>
    </Link>
  );
}
