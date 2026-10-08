import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";

import { AppShell } from "@/components/app/app-shell";
import { AuthGuard } from "@/components/app/auth-guard";
import { Spinner } from "@/components/ui/feedback";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="theme-app flex min-h-screen items-center justify-center bg-bg">
          <Spinner />
        </div>
      }
    >
      <AppShell>
        <AuthGuard>{children}</AuthGuard>
      </AppShell>
    </Suspense>
  );
}
