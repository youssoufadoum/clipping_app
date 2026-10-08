"use client";

import { useState } from "react";

import { PageHeader } from "@/components/app/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { errorMessage } from "@/lib/api";
import { formatDate, formatDateTime, formatMinutes } from "@/lib/format";
import { useUsage, useUsageHistory } from "@/lib/queries";

const EVENT_LABELS: Record<string, string> = {
  source_processed: "Video processed",
  clip_rendered: "Clip exported",
};

function Meter({ label, used, reserved = 0, limit }: { label: string; used: number; reserved?: number; limit: number }) {
  const pct = (n: number) => `${Math.min(100, (n / Math.max(limit, 1)) * 100)}%`;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-sm text-muted">
          {formatMinutes(used)}
          {reserved > 0 && ` + ${formatMinutes(reserved)} reserved`} of {formatMinutes(limit)}
        </span>
      </div>
      <div className="relative mt-2 h-2.5 overflow-hidden rounded-full bg-surface-2">
        <div className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: pct(used) }} />
        {reserved > 0 && (
          <div className="absolute inset-y-0 rounded-full bg-accent/40" style={{ left: pct(used), width: pct(reserved) }} />
        )}
      </div>
    </div>
  );
}

export function UsageView() {
  const usage = useUsage();
  const [page, setPage] = useState(1);
  const history = useUsageHistory(page);

  return (
    <>
      <PageHeader title="Usage & credits" description="Minutes counted on your plan this billing period." />
      <div className="grid gap-6 px-4 py-6 sm:px-8 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          {usage.isPending ? (
            <Skeleton className="h-48" />
          ) : usage.isError ? (
            <ErrorState message={errorMessage(usage.error)} onRetry={() => usage.refetch()} />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>{usage.data.plan.name} plan</CardTitle>
                <CardDescription>
                  Period {formatDate(usage.data.period_start)} – {formatDate(usage.data.period_end)}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <Meter label="Source minutes" used={usage.data.source_minutes_used} limit={usage.data.source_minutes_limit} />
                <Meter
                  label="Export minutes"
                  used={usage.data.render_minutes_used}
                  reserved={usage.data.render_minutes_reserved}
                  limit={usage.data.render_minutes_limit}
                />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Activity</CardTitle>
            </CardHeader>
            <CardContent>
              {history.isPending ? (
                <Skeleton className="h-32" />
              ) : history.isError ? (
                <ErrorState message={errorMessage(history.error)} onRetry={() => history.refetch()} />
              ) : history.data.items.length === 0 ? (
                <EmptyState title="No usage yet" description="Usage appears here when a video is processed or a clip is exported." />
              ) : (
                <>
                  <ul className="divide-y divide-border text-sm">
                    {history.data.items.map((e) => (
                      <li key={e.id} className="flex items-center justify-between py-2.5">
                        <span>
                          {EVENT_LABELS[e.event_type] ?? e.event_type}
                          <span className="block text-xs text-muted">{formatDateTime(e.created_at)}</span>
                        </span>
                        <span className="font-mono">
                          {e.quantity.toFixed(1)} {e.unit === "source_minutes" ? "source min" : "export min"}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {history.data.total > history.data.page_size && (
                    <div className="mt-3 flex justify-between">
                      <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                        Newer
                      </Button>
                      <Button size="sm" variant="secondary" disabled={page * history.data.page_size >= history.data.total} onClick={() => setPage((p) => p + 1)}>
                        Older
                      </Button>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </div>
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>How usage is calculated</CardTitle>
          </CardHeader>
          <CardContent>
            {usage.data ? (
              <ul className="list-disc space-y-2 pl-4 text-sm text-muted">
                {usage.data.policy.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            ) : (
              <Skeleton className="h-24" />
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
