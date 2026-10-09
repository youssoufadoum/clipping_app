"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Minus } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { ErrorState, Skeleton } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { Plan } from "@/lib/types";
import { cn } from "@/lib/utils";

function Row({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      {ok ? <Check className="mt-0.5 size-4 text-success" aria-hidden /> : <Minus className="mt-0.5 size-4 text-muted" aria-hidden />}
      <span className={ok ? "text-fg" : "text-muted"}>{children}</span>
    </li>
  );
}

/** Plan limits come from the API so the page always matches what the server enforces. */
export function PricingTable({ currentPlan }: { currentPlan?: string }) {
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => api<Plan[]>("/api/v1/billing/plans", { auth: false }) });

  if (plans.isPending) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-96" />
        ))}
      </div>
    );
  }
  if (plans.isError) {
    return <ErrorState title="Plans could not be loaded" message={errorMessage(plans.error)} onRetry={() => plans.refetch()} />;
  }
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {plans.data.map((p) => {
          const highlighted = p.code === "creator";
          return (
            <div key={p.code} className={cn("flex flex-col rounded-[var(--radius-card)] border bg-surface p-6", highlighted ? "border-accent shadow-lg" : "border-border")}>
              <h2 className="text-lg font-semibold text-fg">{p.name}</h2>
              <p className="mt-1 min-h-10 text-sm text-muted">{p.description}</p>
              <p className="mt-4 text-2xl font-semibold text-fg">{p.code === "free" ? "Free" : "Paid plan"}</p>
              <ul className="mt-5 flex-1 space-y-2.5">
                <Row ok>{p.monthly_source_minutes.toLocaleString()} source minutes / month</Row>
                <Row ok>{p.monthly_render_minutes.toLocaleString()} export minutes / month</Row>
                <Row ok>{p.monthly_ai_minutes.toLocaleString()} AI minutes / month</Row>
                <Row ok>Uploads up to {(p.max_upload_bytes / 1024 ** 3).toFixed(0)} GB</Row>
                <Row ok>Videos up to {formatDuration(p.max_video_duration_seconds)} long</Row>
                <Row ok={!p.watermark}>{p.watermark ? "Watermarked exports" : "No watermark"}</Row>
                <Row ok={p.priority_processing}>Priority processing</Row>
                <Row ok={p.team_workspace}>Shared team workspace</Row>
              </ul>
              <div className="mt-6">
                {currentPlan === p.code ? (
                  <Button variant="secondary" className="w-full" disabled>
                    Current plan
                  </Button>
                ) : p.code === "free" ? (
                  <Button asChild variant={highlighted ? "primary" : "outline"} className="w-full">
                    <Link href="/register">Start free</Link>
                  </Button>
                ) : p.checkout_available ? (
                  <Button asChild className="w-full">
                    <Link href="/billing">Upgrade</Link>
                  </Button>
                ) : (
                  <Button variant="outline" className="w-full" disabled title="Online checkout is not available yet">
                    Checkout coming soon
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-6 text-center text-sm text-muted">
        Paid plan prices will be shown at checkout once online billing launches. Usage is metered in tenths of a minute, and failed jobs are never charged.
      </p>
    </>
  );
}
