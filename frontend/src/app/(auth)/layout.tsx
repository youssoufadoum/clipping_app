import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/brand/logo";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="theme-app flex min-h-screen flex-col bg-bg text-fg">
      <div aria-hidden className="pointer-events-none fixed inset-0 bg-[radial-gradient(50%_40%_at_50%_0%,rgba(128,100,255,0.18),transparent)]" />
      <header className="relative px-6 py-5">
        <Link href="/" aria-label="Virello Studio home">
          <Logo />
        </Link>
      </header>
      <main id="main" className="relative flex flex-1 items-start justify-center px-4 pb-16 pt-6 sm:items-center sm:pt-0">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
