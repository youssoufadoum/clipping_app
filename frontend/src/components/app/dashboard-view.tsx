"use client";

import { Clapperboard, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/app/app-shell";
import { ProjectCard } from "@/components/app/project-card";
import { LinkImporter } from "@/components/app/link-importer";
import { OrDivider } from "@/components/app/or-divider";
import { Uploader } from "@/components/app/uploader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import { formatMinutes } from "@/lib/format";
import { useMe, useProjects, useUsage } from "@/lib/queries";

const STATUS_FILTERS = [
  ["", "All active"],
  ["ready", "Ready"],
  ["queued", "Queued"],
  ["inspecting", "Processing"],
  ["failed", "Failed"],
  ["draft", "Draft"],
  ["archived", "Archived"],
] as const;

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function UsageCard() {
  const usage = useUsage();
  if (usage.isPending) return <Skeleton className="h-36" />;
  if (usage.isError) return <ErrorState message={errorMessage(usage.error)} onRetry={() => usage.refetch()} />;
  const u = usage.data;
  const bars = [
    { label: "Source minutes", used: u.source_minutes_used, limit: u.source_minutes_limit },
    { label: "Export minutes", used: u.render_minutes_used + u.render_minutes_reserved, limit: u.render_minutes_limit },
  ];
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>This month</CardTitle>
        <Link href="/usage" className="text-xs text-accent hover:underline">
          {u.plan.name} plan
        </Link>
      </CardHeader>
      <CardContent className="space-y-4">
        {bars.map((b) => (
          <div key={b.label}>
            <div className="flex justify-between text-xs">
              <span className="text-muted">{b.label}</span>
              <span>
                {formatMinutes(b.used)} / {formatMinutes(b.limit)}
              </span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2">
              <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, (b.used / Math.max(b.limit, 1)) * 100)}%` }} />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function DashboardView() {
  const me = useMe();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const debouncedQ = useDebounced(q);
  const projects = useProjects({ page, q: debouncedQ || undefined, status: status || undefined });

  const name = me.data?.display_name || me.data?.email?.split("@")[0];
  const totalPages = projects.data ? Math.max(1, Math.ceil(projects.data.total / projects.data.page_size)) : 1;
  const filtering = Boolean(debouncedQ || status);

  return (
    <>
      <PageHeader
        title={name ? `Welcome back, ${name}` : "Dashboard"}
        description="Paste a YouTube link or upload a video to make shorts."
        actions={
          <Button asChild>
            <Link href="/projects/new">
              <Plus /> New project
            </Link>
          </Button>
        }
      />
      <div className="grid gap-6 px-4 py-6 sm:px-8 xl:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-6">
          <LinkImporter />
          <OrDivider />
          <Uploader compact />

          <section aria-labelledby="projects-heading" className="space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <h2 id="projects-heading" className="text-lg font-semibold">
                Projects
              </h2>
              <div className="flex gap-2">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
                  <Input value={q} onChange={(e) => {
                      setQ(e.target.value);
                      setPage(1);
                    }} placeholder="Search projects" aria-label="Search projects" className="w-full pl-9 sm:w-56" />
                </div>
                <Select value={status} onChange={(e) => {
                    setStatus(e.target.value);
                    setPage(1);
                  }} aria-label="Filter by status" className="w-36">
                  {STATUS_FILTERS.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            {projects.isPending ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-56" />
                ))}
              </div>
            ) : projects.isError ? (
              <ErrorState title="Projects could not be loaded" message={errorMessage(projects.error)} onRetry={() => projects.refetch()} />
            ) : projects.data.items.length === 0 ? (
              filtering ? (
                <EmptyState icon={<Search />} title="No matching projects" description="Try a different search or filter." />
              ) : (
                <EmptyState
                  icon={<Clapperboard />}
                  title="No projects yet"
                  description="Upload your first long video above. Once it's processed you can cut it into clips for every platform."
                />
              )
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {projects.data.items.map((p) => (
                    <ProjectCard key={p.id} project={p} />
                  ))}
                </div>
                {totalPages > 1 && (
                  <nav aria-label="Pagination" className="flex items-center justify-center gap-3 text-sm">
                    <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                      Previous
                    </Button>
                    <span className="text-muted">
                      Page {page} of {totalPages}
                    </span>
                    <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                      Next
                    </Button>
                  </nav>
                )}
              </>
            )}
          </section>
        </div>
        <aside className="space-y-4">
          <UsageCard />
          <Card>
            <CardHeader>
              <CardTitle>Tips</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-2 pl-4 text-sm text-muted">
                <li>Vertical 9:16 works best for TikTok, Shorts and Reels.</li>
                <li>Slide the crop window to keep the speaker centered.</li>
                <li>Clips between 20 and 60 seconds are a good starting point.</li>
              </ul>
            </CardContent>
          </Card>
        </aside>
      </div>
    </>
  );
}
