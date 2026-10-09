"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/components/ui/toast";
import { api, errorMessage, getApiToken } from "@/lib/api";
import { config } from "@/lib/config";
import { keys } from "@/lib/queries";
import type { Clip, Job, SignedUrl } from "@/lib/types";

export function useRenderClip(projectId: string) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (clipId: string) => api<Job>(`/api/v1/clips/${clipId}/render`, { method: "POST" }),
    onSuccess: (_job, clipId) => {
      toast("Render started");
      qc.invalidateQueries({ queryKey: keys.clips(projectId) });
      qc.invalidateQueries({ queryKey: keys.clip(clipId) });
      qc.invalidateQueries({ queryKey: keys.usage });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });
}

export function useDuplicateClip(projectId: string) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (clipId: string) => api<Clip>(`/api/v1/clips/${clipId}/duplicate`, { method: "POST" }),
    onSuccess: () => {
      toast("Clip duplicated");
      qc.invalidateQueries({ queryKey: keys.clips(projectId) });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });
}

export function useDeleteClip(projectId: string) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (clipId: string) => api<void>(`/api/v1/clips/${clipId}`, { method: "DELETE" }),
    onSuccess: () => {
      toast("Clip deleted");
      qc.invalidateQueries({ queryKey: keys.clips(projectId) });
      qc.invalidateQueries({ queryKey: keys.project(projectId) });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });
}

/** Fetch a fresh short-lived download link and start the browser download. */
export async function downloadClip(clipId: string): Promise<void> {
  const link = await api<SignedUrl>(`/api/v1/clips/${clipId}/download`);
  const a = document.createElement("a");
  a.href = link.url;
  a.rel = "noopener";
  if (link.filename) a.download = link.filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** Subtitle files need the auth header, so fetch them and save via a blob URL. */
export async function downloadSubtitles(clipId: string, format: "srt" | "vtt"): Promise<void> {
  const token = await getApiToken();
  const res = await fetch(`${config.apiBaseUrl}/api/v1/clips/${clipId}/subtitles?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(res.status === 404 ? "No transcript is available for this clip." : "Subtitles could not be downloaded.");
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? `captions.${format}`;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
