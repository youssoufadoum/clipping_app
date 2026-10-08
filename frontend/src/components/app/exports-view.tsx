"use client";

import { Download, FileVideo, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/app/app-shell";
import { ConfirmDialog } from "@/components/app/confirm-dialog";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { formatBytes, formatDateTime, formatDuration } from "@/lib/format";
import { useExports } from "@/lib/queries";
import type { SignedUrl } from "@/lib/types";

export function ExportsView() {
  const [page, setPage] = useState(1);
  const exports = useExports(page);
  const toast = useToast();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  const download = async (id: string) => {
    setBusy(id);
    try {
      const link = await api<SignedUrl>(`/api/v1/exports/${id}`);
      const a = document.createElement("a");
      a.href = link.url;
      if (link.filename) a.download = link.filename;
      a.click();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };

  const totalPages = exports.data ? Math.max(1, Math.ceil(exports.data.total / exports.data.page_size)) : 1;

  return (
    <>
      <PageHeader title="Exports" description="Every MP4 you have rendered, newest first." />
      <div className="px-4 py-6 sm:px-8">
        {exports.isPending ? (
          <Skeleton className="h-40" />
        ) : exports.isError ? (
          <ErrorState message={errorMessage(exports.error)} onRetry={() => exports.refetch()} />
        ) : exports.data.items.length === 0 ? (
          <EmptyState
            icon={<FileVideo />}
            title="No exports yet"
            description="Render a clip from any project and it will appear here."
            action={
              <Button asChild variant="secondary">
                <Link href="/dashboard">Go to projects</Link>
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-[var(--radius-card)] border border-border">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-surface text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Created</th>
                  <th className="px-4 py-3 font-medium">Resolution</th>
                  <th className="px-4 py-3 font-medium">Length</th>
                  <th className="px-4 py-3 font-medium">Size</th>
                  <th className="px-4 py-3 font-medium">Project</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {exports.data.items.map((e) => (
                  <tr key={e.id}>
                    <td className="px-4 py-3">{formatDateTime(e.created_at)}</td>
                    <td className="px-4 py-3">{e.width} × {e.height}</td>
                    <td className="px-4 py-3">{formatDuration(e.duration_seconds)}</td>
                    <td className="px-4 py-3">{formatBytes(e.size_bytes)}</td>
                    <td className="px-4 py-3">
                      <Link href={`/projects/${e.project_id}${e.clip_id ? `/clips/${e.clip_id}` : ""}`} className="text-accent hover:underline">
                        Open
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="secondary" loading={busy === e.id} onClick={() => download(e.id)}>
                          <Download /> Download
                        </Button>
                        <ConfirmDialog
                          title="Delete export?"
                          description="This removes the rendered file. The clip itself is kept and can be rendered again."
                          onConfirm={async () => {
                            await api(`/api/v1/media/${e.id}`, { method: "DELETE" });
                            toast("Export deleted");
                            qc.invalidateQueries({ queryKey: ["exports"] });
                          }}
                          trigger={
                            <Button size="icon" variant="ghost" aria-label="Delete export">
                              <Trash2 />
                            </Button>
                          }
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {totalPages > 1 && (
          <nav aria-label="Pagination" className="mt-4 flex items-center justify-center gap-3 text-sm">
            <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className="text-muted">Page {page} of {totalPages}</span>
            <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </nav>
        )}
      </div>
    </>
  );
}
