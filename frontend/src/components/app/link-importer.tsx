"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link2, PlaySquare } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ShortsPicker, shortsPayload, type ShortsChoice } from "@/components/app/shorts-picker";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { api, errorMessage } from "@/lib/api";
import { useSystemStatus } from "@/lib/queries";
import type { Job, Project } from "@/lib/types";
import { parseYouTubeId } from "@/lib/youtube";

/** Paste a YouTube link; the server downloads it and (optionally) makes AI shorts. */
export function LinkImporter({ title }: { title?: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const system = useSystemStatus();
  const aiAvailable = system.data?.ai_available === true;
  const [url, setUrl] = useState("");
  const [touched, setTouched] = useState(false);
  const [rights, setRights] = useState(false);
  const [shorts, setShorts] = useState<ShortsChoice>("30");
  const videoId = parseYouTubeId(url);
  const urlError = touched && url.trim() && !videoId ? "Paste a link to a single YouTube video, like youtube.com/watch?v=… or youtu.be/…" : null;

  const start = useMutation({
    mutationFn: () =>
      api<{ project: Project; job: Job }>("/api/v1/projects/import", {
        body: {
          url: url.trim(),
          rights_confirmed: rights,
          title: title?.trim() || null,
          auto_shorts: aiAvailable ? shortsPayload(shorts) : undefined,
        },
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      router.push(`/projects/${res.project.id}`);
    },
  });

  if (system.data && !system.data.youtube_import) return null;

  return (
    <form
      className="space-y-3 rounded-[var(--radius-card)] border border-border bg-surface p-5"
      onSubmit={(e) => {
        e.preventDefault();
        setTouched(true);
        if (videoId && rights) start.mutate();
      }}
    >
      <label htmlFor="youtube-url" className="flex items-center gap-2 font-medium">
        <PlaySquare className="size-5 text-accent" aria-hidden /> Paste a YouTube link
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Link2 className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input
            id="youtube-url"
            inputMode="url"
            autoComplete="off"
            placeholder="https://www.youtube.com/watch?v=…"
            className="h-11 pl-9"
            value={url}
            aria-invalid={!!urlError}
            aria-describedby="youtube-url-error"
            onChange={(e) => setUrl(e.target.value)}
            onBlur={() => setTouched(true)}
          />
        </div>
        <Button type="submit" size="lg" className="h-11" loading={start.isPending} disabled={!videoId || !rights}>
          {aiAvailable && shorts !== "off" ? "Make shorts" : "Import video"}
        </Button>
      </div>
      {urlError && (
        <p id="youtube-url-error" role="alert" className="text-xs text-danger">
          {urlError}
        </p>
      )}
      {aiAvailable && <ShortsPicker value={shorts} onChange={setShorts} />}
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-0.5 accent-[var(--accent)]" checked={rights} onChange={(e) => setRights(e.target.checked)} />
        <span>
          I own this video or have permission to use it.
          <span className="block text-xs text-muted">
            Downloading from YouTube is limited by YouTube&apos;s Terms of Service. Private, age-restricted and members-only videos can&apos;t
            be imported.
          </span>
        </span>
      </label>
      {start.isError && <Alert variant="danger">{errorMessage(start.error)}</Alert>}
    </form>
  );
}
