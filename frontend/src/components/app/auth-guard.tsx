"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Spinner } from "@/components/ui/feedback";
import { useAuth } from "@/lib/auth/provider";

/**
 * Client-side route protection for UX. Authorization is enforced by the API on
 * every request; this only avoids rendering private screens to signed-out users.
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "unauthenticated") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Spinner label={status === "loading" ? "Loading your workspace" : "Redirecting to sign in"} />
      </div>
    );
  }
  return <>{children}</>;
}
