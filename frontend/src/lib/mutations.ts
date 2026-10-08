"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
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
