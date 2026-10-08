import type { Metadata } from "next";
import Link from "next/link";

import { FEATURES, STEPS } from "@/components/site/content";
import { AvailabilityBadge, PageHero, Section, SectionHeading } from "@/components/site/marketing";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Features" };

export default function FeaturesPage() {
  const available = FEATURES.filter((f) => f.available);
  const upcoming = FEATURES.filter((f) => !f.available);
  return (
    <>
      <PageHero title="Features" description="What Virello Studio does today, and what we are building next." />
      {[
        { title: "Available now", items: available },
        { title: "In development", items: upcoming },
      ].map((group) => (
        <Section key={group.title} className="py-12">
          <h2 className="text-2xl font-semibold text-fg">{group.title}</h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {group.items.map((f) => (
              <div key={f.title} className="rounded-[var(--radius-card)] border border-border bg-surface p-5">
                <div className="flex items-start justify-between">
                  <f.icon className="size-6 text-accent" aria-hidden />
                  <AvailabilityBadge available={f.available} />
                </div>
                <h3 className="mt-4 font-semibold text-fg">{f.title}</h3>
                <p className="mt-1.5 text-sm text-muted">{f.description}</p>
              </div>
            ))}
          </div>
        </Section>
      ))}
      <div className="border-t border-border bg-bg-subtle">
        <Section id="how-it-works">
          <SectionHeading title="How it works" />
          <ol className="mx-auto mt-10 max-w-2xl space-y-4">
            {STEPS.map((s, i) => (
              <li key={s.title} className="flex gap-4 rounded-[var(--radius-card)] border border-border bg-surface p-5">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-fg">{i + 1}</span>
                <div>
                  <h3 className="font-semibold text-fg">{s.title}</h3>
                  <p className="mt-1 text-sm text-muted">{s.description}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="mt-10 text-center">
            <Button asChild size="lg">
              <Link href="/register">Start creating</Link>
            </Button>
          </div>
        </Section>
      </div>
    </>
  );
}
