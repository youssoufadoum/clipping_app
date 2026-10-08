import type { Metadata } from "next";

import { FAQS } from "@/components/site/content";
import { PageHero } from "@/components/site/marketing";

export const metadata: Metadata = { title: "FAQ" };

export default function FaqPage() {
  return (
    <>
      <PageHero title="Frequently asked questions" description="Straight answers about what Virello Studio does and how it handles your content." />
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <div className="divide-y divide-border rounded-[var(--radius-card)] border border-border bg-surface">
          {FAQS.map((f) => (
            <details key={f.q} className="p-5">
              <summary className="cursor-pointer font-medium text-fg">{f.q}</summary>
              <p className="mt-2 text-sm text-muted">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </>
  );
}
