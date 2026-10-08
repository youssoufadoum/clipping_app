"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert, Spinner } from "@/components/ui/feedback";
import { useAuth } from "@/lib/auth/provider";
import { safeNext } from "@/lib/redirect";

/** Landing page for email confirmation, OAuth and password-recovery links. */
export function AuthCallback() {
  const { status } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [timedOut, setTimedOut] = useState(false);
  const providerError = params.get("error_description") ?? params.get("error");

  useEffect(() => {
    if (status === "authenticated") router.replace(safeNext(params.get("next"), "/onboarding"));
  }, [status, params, router]);

  useEffect(() => {
    const t = setTimeout(() => setTimedOut(true), 8000);
    return () => clearTimeout(t);
  }, []);

  if (providerError || (timedOut && status !== "authenticated")) {
    return (
      <Alert variant="danger" title="We couldn't complete sign-in">
        {providerError ?? "The link may have expired."} <Link href="/login" className="text-accent underline">Back to sign in</Link>
      </Alert>
    );
  }
  return <Spinner label="Signing you in" />;
}
