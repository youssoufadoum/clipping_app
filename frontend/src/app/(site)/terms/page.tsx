import type { Metadata } from "next";

import { PageHero, Prose } from "@/components/site/marketing";

export const metadata: Metadata = { title: "Terms of service" };

export default function TermsPage() {
  return (
    <>
      <PageHero title="Terms of service" description="The rules for using Virello Studio." />
      <Prose>
        <p>
          <em>Template terms for the software as built. Operators must review them with legal counsel before going live.</em>
        </p>
        <h2>Your account</h2>
        <p>You are responsible for keeping your credentials secure and for activity under your account.</p>
        <h2>Your content</h2>
        <p>
          You keep all rights to the videos you upload. You grant us a limited license to store and process them only to provide the
          service to you. You confirm you have the rights and permissions needed to upload and process every file, including any
          video you import by link. Importing from YouTube is subject to YouTube&apos;s own Terms of Service; only import videos
          you own or are authorized to use.
        </p>
        <h2>Acceptable use</h2>
        <ul>
          <li>No unlawful, infringing, or harmful content.</li>
          <li>No attempts to bypass plan limits, access other users&apos; data, or disrupt the service.</li>
          <li>No automated abuse of the API beyond published rate limits.</li>
        </ul>
        <h2>Plans and usage</h2>
        <p>
          Plan limits are enforced by the service and shown in your account. We may change plans with notice. Failed or cancelled jobs
          are not charged.
        </p>
        <h2>No guarantees of results</h2>
        <p>
          Any scores or suggestions are estimates to help you decide. We do not guarantee views, engagement or other outcomes.
        </p>
        <h2>Termination</h2>
        <p>You may delete your account at any time. We may suspend accounts that violate these terms.</p>
        <h2>Liability</h2>
        <p>The service is provided &quot;as is&quot; to the extent permitted by law.</p>
      </Prose>
    </>
  );
}
