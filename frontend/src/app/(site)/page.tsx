import { ArrowRight, PlayCircle } from "lucide-react";
import Link from "next/link";

import { FAQS, FEATURES, STEPS, USE_CASES } from "@/components/site/content";
import { AvailabilityBadge, Section, SectionHeading } from "@/components/site/marketing";
import { ProductPreview } from "@/components/site/product-preview";
import { Button } from "@/components/ui/button";

export default function HomePage() {
  return (
    <>
      <div className="relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[520px] bg-[radial-gradient(60%_60%_at_50%_0%,rgba(109,74,255,0.14),transparent)]" />
        <Section className="relative pb-10 pt-16 text-center sm:pt-24">
          <p className="mx-auto inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-muted">
            <span className="size-1.5 rounded-full bg-accent" /> Upload, trim, reframe, export
          </p>
          <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-semibold tracking-tight text-fg sm:text-6xl">
            Turn one long video into a week of content.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-muted">
            Virello Studio turns podcasts, webinars and interviews into short clips for TikTok, YouTube Shorts,
            Reels and LinkedIn. Mark your moments, reframe for each platform, and export polished MP4s. AI clip
            discovery and captions are on the way.
          </p>
          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <Button asChild size="lg">
              <Link href="/register">
                Start creating <ArrowRight />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="#how-it-works">
                <PlayCircle /> See how it works
              </Link>
            </Button>
          </div>
        </Section>
        <div className="px-4 pb-16 sm:px-6">
          <ProductPreview />
        </div>
      </div>

      <div className="border-y border-border bg-bg-subtle">
        <Section id="features">
          <SectionHeading eyebrow="Features" title="Everything between the long recording and the short clip" description="Available features are ready to use today. Features in development are labeled so you always know what to expect." />
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.slice(0, 9).map((f) => (
              <div key={f.title} className="rounded-[var(--radius-card)] border border-border bg-surface p-5">
                <div className="flex items-start justify-between gap-3">
                  <span className="flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent">
                    <f.icon className="size-5" aria-hidden />
                  </span>
                  <AvailabilityBadge available={f.available} />
                </div>
                <h3 className="mt-4 font-semibold text-fg">{f.title}</h3>
                <p className="mt-1.5 text-sm text-muted">{f.description}</p>
              </div>
            ))}
          </div>
          <div className="mt-8 text-center">
            <Button asChild variant="link">
              <Link href="/features">
                See all features <ArrowRight />
              </Link>
            </Button>
          </div>
        </Section>
      </div>

      <Section id="how-it-works">
        <SectionHeading eyebrow="How it works" title="Three steps from upload to export" />
        <ol className="mt-12 grid gap-6 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="relative rounded-[var(--radius-card)] border border-border bg-surface p-6">
              <span className="flex size-9 items-center justify-center rounded-full bg-fg text-sm font-semibold text-bg">{i + 1}</span>
              <h3 className="mt-4 text-lg font-semibold text-fg">{s.title}</h3>
              <p className="mt-2 text-sm text-muted">{s.description}</p>
            </li>
          ))}
        </ol>
      </Section>

      <div className="border-y border-border bg-bg-subtle">
        <Section id="use-cases">
          <SectionHeading eyebrow="Use cases" title="Built for people who publish every week" />
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {USE_CASES.map((u) => (
              <div key={u.title} className="rounded-[var(--radius-card)] border border-border bg-surface p-5">
                <h3 className="font-semibold text-fg">{u.title}</h3>
                <p className="mt-2 text-sm text-muted">{u.description}</p>
              </div>
            ))}
          </div>
        </Section>
      </div>

      <Section>
        <SectionHeading eyebrow="FAQ" title="Common questions" />
        <div className="mx-auto mt-10 max-w-3xl divide-y divide-border rounded-[var(--radius-card)] border border-border bg-surface">
          {FAQS.slice(0, 4).map((f) => (
            <details key={f.q} className="group p-5">
              <summary className="cursor-pointer list-none font-medium text-fg marker:hidden">{f.q}</summary>
              <p className="mt-2 text-sm text-muted">{f.a}</p>
            </details>
          ))}
        </div>
        <p className="mt-6 text-center text-sm text-muted">
          More answers on the <Link className="text-accent hover:underline" href="/faq">FAQ page</Link>.
        </p>
      </Section>

      <Section className="pb-24">
        <div className="theme-app rounded-2xl border border-border bg-bg px-6 py-14 text-center sm:px-12">
          <h2 className="text-3xl font-semibold tracking-tight text-fg">Your next week of content is already recorded.</h2>
          <p className="mx-auto mt-3 max-w-xl text-muted">Create a free account and turn your latest long video into clips today.</p>
          <Button asChild size="lg" className="mt-8">
            <Link href="/register">
              Start creating <ArrowRight />
            </Link>
          </Button>
        </div>
      </Section>
    </>
  );
}
