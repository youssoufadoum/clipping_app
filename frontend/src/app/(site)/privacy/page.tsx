import type { Metadata } from "next";

import { PageHero, Prose } from "@/components/site/marketing";

export const metadata: Metadata = { title: "Privacy policy" };

export default function PrivacyPage() {
  return (
    <>
      <PageHero title="Privacy policy" description="How Virello Studio collects, uses and protects your information." />
      <Prose>
        <p>
          <em>This policy describes the software as built. Operators deploying Virello Studio must review it with legal counsel and
          complete the controller details before going live.</em>
        </p>
        <h2>What we collect</h2>
        <ul>
          <li>Account information: email address, display name and the onboarding answers you choose to give.</li>
          <li>Content: the videos you upload and the clips, thumbnails and exports derived from them.</li>
          <li>Usage records: processing minutes, job history and timestamps needed to enforce plan limits.</li>
          <li>Technical logs: request metadata and error reports, with secrets and signed links redacted.</li>
        </ul>
        <h2>How we use it</h2>
        <p>
          We use your information to run the service: storing and processing your videos, showing your projects, enforcing plan limits,
          securing accounts and responding to support requests. We do not sell personal information.
        </p>
        <h2>Processing by third parties</h2>
        <p>
          Authentication, including email verification codes, is provided by Supabase. Media is kept in private object storage. When
          you use AI shorts, your video&apos;s audio and its transcript are sent to Google&apos;s Gemini API solely to transcribe the
          video and pick moments for you. Payment details, when billing is enabled, are handled by Stripe and never touch our servers.
        </p>
        <h2>Storage and security</h2>
        <p>
          Media is stored in private buckets and served only through links that expire within minutes. Data is encrypted in transit.
          Virello Studio does not offer end-to-end encryption.
        </p>
        <h2>Retention and deletion</h2>
        <p>
          Your content is kept until you delete it or for the retention period configured by the operator. Deleting a project removes its
          media immediately. Deleting your account removes your projects, media, usage records and sign-in.
        </p>
        <h2>Your rights</h2>
        <p>
          Depending on where you live you may have rights to access, correct, export or delete your data. Use the in-app tools or contact
          us to exercise them.
        </p>
        <h2>Your responsibilities</h2>
        <p>Only upload content you own or have permission to process.</p>
      </Prose>
    </>
  );
}
