import { Mail } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { PageHero } from "@/components/site/marketing";
import { Alert } from "@/components/ui/feedback";
import { config } from "@/lib/config";

export const metadata: Metadata = { title: "Contact" };

export default function ContactPage() {
  return (
    <>
      <PageHero title="Contact us" description="Questions about the product, your account or your data? We're happy to help." />
      <div className="mx-auto max-w-xl px-4 py-12 sm:px-6">
        {config.supportEmail ? (
          <div className="rounded-[var(--radius-card)] border border-border bg-surface p-6 text-center">
            <Mail className="mx-auto size-8 text-accent" aria-hidden />
            <p className="mt-3 text-muted">Email our team and we&apos;ll get back to you.</p>
            <a href={`mailto:${config.supportEmail}`} className="mt-2 inline-block text-lg font-medium text-accent hover:underline">
              {config.supportEmail}
            </a>
          </div>
        ) : (
          <Alert variant="warning" title="Support contact not configured">
            This deployment has no support email configured. Operators: set NEXT_PUBLIC_SUPPORT_EMAIL.
          </Alert>
        )}
        <p className="mt-6 text-center text-sm text-muted">
          Looking for answers right away? Visit the <Link href="/help" className="text-accent hover:underline">help center</Link> or the{" "}
          <Link href="/faq" className="text-accent hover:underline">FAQ</Link>.
        </p>
      </div>
    </>
  );
}
