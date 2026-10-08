"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { ACTIVE_STATUSES } from "@/components/status-badge";
import { api } from "@/lib/api";
import type { Clip, Job, MediaAsset, Page, Profile, Project, Usage, UsageEvent } from "@/lib/types";

export const keys = {
  me: ["me"] as const,
  usage: ["usage"] as const,
  usageHistory: (page: number) => ["usage-history", page] as const,
  projects: (params: Record<string, string | number | undefined>) => ["projects", params] as const,
  project: (id: string) => ["project", id] as const,
  clips: (projectId: string) => ["clips", projectId] as const,
  clip: (id: string) => ["clip", id] as const,
  jobs: (projectId: string) => ["jobs", projectId] as const,
  exports: (page: number) => ["exports", page] as const,
};

/** Poll only while real work is in progress; the interval reflects job state, not a timer-driven fake. */
const POLL_MS = 2000;

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => api<Profile>("/api/v1/me") });
}

export function useUsage(enabled = true) {
  return useQuery({ queryKey: keys.usage, queryFn: () => api<Usage>("/api/v1/usage"), enabled });
}

export function useUsageHistory(page: number) {
  return useQuery({
    queryKey: keys.usageHistory(page),
    queryFn: () => api<Page<UsageEvent>>(`/api/v1/usage/history?page=${page}&page_size=25`),
    placeholderData: keepPreviousData,
  });
}

export function useProjects(params: { page: number; q?: string; status?: string }) {
  const search = new URLSearchParams({ page: String(params.page), page_size: "12" });
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  return useQuery({
    queryKey: keys.projects(params),
    queryFn: () => api<Page<Project>>(`/api/v1/projects?${search}`),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.items.some((p) => ACTIVE_STATUSES.has(p.status)) ? POLL_MS * 2 : false),
  });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: keys.project(id),
    queryFn: () => api<Project>(`/api/v1/projects/${id}`),
    refetchInterval: (q) => {
      const p = q.state.data;
      if (!p) return false;
      const jobActive = p.latest_job && (p.latest_job.status === "queued" || p.latest_job.status === "running");
      return ACTIVE_STATUSES.has(p.status) || jobActive ? POLL_MS : false;
    },
  });
}

export function useClips(projectId: string, enabled = true) {
  return useQuery({
    queryKey: keys.clips(projectId),
    queryFn: () => api<Clip[]>(`/api/v1/projects/${projectId}/clips`),
    enabled,
    refetchInterval: (q) => (q.state.data?.some((c) => c.status === "queued" || c.status === "rendering") ? POLL_MS : false),
  });
}

export function useClip(id: string) {
  return useQuery({
    queryKey: keys.clip(id),
    queryFn: () => api<Clip>(`/api/v1/clips/${id}`),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "rendering" ? POLL_MS : false;
    },
  });
}

export function useJobs(projectId: string) {
  return useQuery({ queryKey: keys.jobs(projectId), queryFn: () => api<Job[]>(`/api/v1/projects/${projectId}/jobs?limit=20`) });
}

export function useExports(page: number) {
  return useQuery({
    queryKey: keys.exports(page),
    queryFn: () => api<Page<MediaAsset>>(`/api/v1/exports?page=${page}&page_size=20`),
    placeholderData: keepPreviousData,
  });
}
