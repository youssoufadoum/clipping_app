import type { Metadata } from "next";
import { Suspense } from "react";

import { VerifyEmailForm } from "@/components/auth/verify-email";
import { Spinner } from "@/components/ui/feedback";

export const metadata: Metadata = { title: "Verify your email" };

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <VerifyEmailForm />
    </Suspense>
  );
}
