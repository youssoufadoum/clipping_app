import { AlertTriangle, CheckCircle2, Info, Loader2, RotateCcw, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const tone = {
  info: { cls: "border-accent/30 bg-accent-soft text-fg", Icon: Info },
  success: { cls: "border-success/30 bg-success-soft text-fg", Icon: CheckCircle2 },
  warning: { cls: "border-warning/30 bg-warning-soft text-fg", Icon: AlertTriangle },
  danger: { cls: "border-danger/30 bg-danger-soft text-fg", Icon: XCircle },
};

export function Alert({
  variant = "info",
  title,
  children,
  action,
  className,
}: {
  variant?: keyof typeof tone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const { cls, Icon } = tone[variant];
  return (
    <div role={variant === "danger" ? "alert" : "status"} className={cn("flex gap-3 rounded-lg border p-3 text-sm", cls, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="flex-1 space-y-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="text-muted">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-sm text-muted", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span>{label}…</span>
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-surface-2", className)} />;
}

export function Progress({ value, label, className }: { value: number; label?: string; className?: string }) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div className={cn("w-full", className)}>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={label ?? "Progress"}
        className="h-2 w-full overflow-hidden rounded-full bg-surface-2"
      >
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 rounded-[var(--radius-card)] border border-dashed border-border px-6 py-12 text-center", className)}>
      {icon && <div className="text-muted [&_svg]:size-8">{icon}</div>}
      <div className="space-y-1">
        <p className="font-medium text-fg">{title}</p>
        {description && <p className="mx-auto max-w-sm text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Alert
      variant="danger"
      title={title}
      action={
        onRetry && (
          <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 text-sm font-medium text-fg hover:underline">
            <RotateCcw className="size-3.5" aria-hidden /> Retry
          </button>
        )
      }
    >
      {message}
    </Alert>
  );
}
