import { Check } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Section({ id, className, children }: { id?: string; className?: string; children: ReactNode }) {
  return (
    <section id={id} className={cn("mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 sm:py-20", className)}>
      {children}
    </section>
  );
}

export function SectionHeading({ eyebrow, title, description }: { eyebrow?: string; title: string; description?: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      {eyebrow && <p className="text-sm font-semibold uppercase tracking-wider text-accent">{eyebrow}</p>}
      <h2 className="mt-2 text-3xl font-semibold tracking-tight text-fg sm:text-4xl">{title}</h2>
      {description && <p className="mt-4 text-base text-muted sm:text-lg">{description}</p>}
    </div>
  );
}

export function AvailabilityBadge({ available }: { available: boolean }) {
  return available ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-success-soft px-2 py-0.5 text-xs font-medium text-success">
      <Check className="size-3" aria-hidden /> Available now
    </span>
  ) : (
    <span className="inline-flex rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-muted">In development</span>
  );
}

export function PageHero({ title, description }: { title: string; description: string }) {
  return (
    <div className="border-b border-border bg-bg-subtle">
      <div className="mx-auto max-w-3xl px-4 py-14 text-center sm:px-6 sm:py-20">
        <h1 className="text-4xl font-semibold tracking-tight text-fg sm:text-5xl">{title}</h1>
        <p className="mt-4 text-lg text-muted">{description}</p>
      </div>
    </div>
  );
}

export function Prose({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 [&_h2]:mt-10 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-fg [&_li]:mt-1 [&_p]:mt-4 [&_p]:text-muted [&_ul]:mt-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:text-muted">
      {children}
    </div>
  );
}
