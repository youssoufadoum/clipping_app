import { Suspense } from "react";

import { AuthCallback } from "@/components/auth/auth-callback";
import { Spinner } from "@/components/ui/feedback";

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<Spinner label="Signing you in" />}>
      <AuthCallback />
    </Suspense>
  );
}
