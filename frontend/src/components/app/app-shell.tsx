"use client";

import { BarChart3, CreditCard, Download, HelpCircle, LayoutDashboard, LogOut, Menu, Plus, Settings, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/provider";
import { formatMinutes } from "@/lib/format";
import { useUsage } from "@/lib/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/exports", label: "Exports", icon: Download },
  { href: "/usage", label: "Usage", icon: BarChart3 },
  { href: "/billing", label: "Plans & billing", icon: CreditCard },
  { href: "/settings", label: "Settings", icon: Settings },
];

function UsageMini() {
  const { status } = useAuth();
  const usage = useUsage(status === "authenticated");
  if (!usage.data) return null;
  const u = usage.data;
  const pct = u.source_minutes_limit ? Math.min(1, u.source_minutes_used / u.source_minutes_limit) : 0;
  return (
    <Link href="/usage" className="block rounded-lg border border-border bg-surface p-3 text-xs hover:border-border-strong">
      <div className="flex justify-between text-muted">
        <span>{u.plan.name} plan</span>
        <span>{formatMinutes(u.source_minutes_remaining)} left</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct * 100}%` }} />
      </div>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);

  const nav = (
    <nav aria-label="App" className="flex flex-1 flex-col gap-1">
      <Button asChild className="mb-4 w-full justify-start">
        <Link href="/projects/new" onClick={() => setOpen(false)}>
          <Plus /> New project
        </Link>
      </Button>
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || (href === "/dashboard" && pathname.startsWith("/projects"));
        return (
          <Link
            key={href}
            href={href}
            onClick={() => setOpen(false)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
              active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface hover:text-fg",
            )}
          >
            <Icon className="size-4" aria-hidden /> {label}
          </Link>
        );
      })}
      <Link href="/help" className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted hover:bg-surface hover:text-fg">
        <HelpCircle className="size-4" aria-hidden /> Help & support
      </Link>
      <div className="mt-auto space-y-3 pt-6">
        <UsageMini />
        <div className="flex items-center justify-between gap-2 rounded-lg px-1">
          <span className="truncate text-xs text-muted" title={user?.email ?? undefined}>
            {user?.email}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Sign out"
            onClick={async () => {
              await signOut();
              router.replace("/login");
            }}
          >
            <LogOut />
          </Button>
        </div>
      </div>
    </nav>
  );

  return (
    <div className="theme-app flex min-h-screen bg-bg text-fg">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border bg-bg-subtle p-4 lg:flex">
        <Link href="/dashboard" className="mb-6 px-1" aria-label="Dashboard">
          <Logo />
        </Link>
        {nav}
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} aria-hidden />
          <aside className="relative flex h-full w-72 flex-col border-r border-border bg-bg-subtle p-4">
            <div className="mb-6 flex items-center justify-between">
              <Logo />
              <Button variant="ghost" size="icon" aria-label="Close menu" onClick={() => setOpen(false)}>
                <X />
              </Button>
            </div>
            {nav}
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-bg/90 px-4 backdrop-blur lg:hidden">
          <Button variant="ghost" size="icon" aria-label="Open menu" onClick={() => setOpen(true)}>
            <Menu />
          </Button>
          <Logo compact />
        </header>
        <main id="main" className="flex-1">
          {children}
        </main>
      </div>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 border-b border-border px-4 py-6 sm:flex-row sm:items-end sm:justify-between sm:px-8">
      <div className="min-w-0 space-y-1">
        <h1 className="truncate text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <div className="text-sm text-muted">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
