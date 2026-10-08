import type { Metadata } from "next";

import { PageHero, Prose } from "@/components/site/marketing";

export const metadata: Metadata = { title: "Cookies & data" };

export default function CookiesPage() {
  return (
    <>
      <PageHero title="Cookies and local data" description="What Virello Studio stores in your browser." />
      <Prose>
        <h2>Essential storage only</h2>
        <p>
          Virello Studio stores your sign-in session in your browser&apos;s local storage so you stay signed in. It is required for the
          app to work and is removed when you sign out.
        </p>
        <h2>No advertising or tracking cookies</h2>
        <p>We do not use advertising cookies or third-party trackers.</p>
        <h2>Error monitoring</h2>
        <p>
          When enabled by the operator, error reports help us fix problems. They exclude passwords, tokens and signed media links.
        </p>
      </Prose>
    </>
  );
}
