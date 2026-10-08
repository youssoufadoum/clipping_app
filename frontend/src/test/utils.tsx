import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/lib/auth/provider";
import type { AuthClient, AuthUser } from "@/lib/auth/types";

export function fakeAuthClient(user: AuthUser | null = { id: "u1", email: "ada@example.com" }): AuthClient {
  let current = user;
  const listeners = new Set<(u: AuthUser | null) => void>();
  return {
    mode: "local",
    supportsPasswordReset: false,
    supportsOAuth: false,
    getUser: vi.fn(async () => current),
    getAccessToken: vi.fn(async () => (current ? "test-token" : null)),
    signIn: vi.fn(async (email: string) => {
      current = { id: "u1", email };
      listeners.forEach((l) => l(current));
    }),
    signUp: vi.fn(async () => ({ needsEmailConfirmation: false })),
    signOut: vi.fn(async () => {
      current = null;
    }),
    signInWithGoogle: vi.fn(),
    requestPasswordReset: vi.fn(),
    updatePassword: vi.fn(),
    onChange: (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
}

export function renderWithProviders(ui: ReactElement, client: AuthClient = fakeAuthClient()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return {
    client,
    ...render(
      <QueryClientProvider client={qc}>
        <AuthProvider client={client}>
          <ToastProvider>{ui}</ToastProvider>
        </AuthProvider>
      </QueryClientProvider>,
    ),
  };
}

/** Route fetch calls to handlers keyed by "METHOD path". */
export function mockFetch(handlers: Record<string, (body: unknown) => { status?: number; json?: unknown }>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const key = `${init?.method ?? "GET"} ${url.pathname}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`Unexpected request ${key}`);
    const res = handler(init?.body ? JSON.parse(String(init.body)) : undefined);
    const status = res.status ?? 200;
    return new Response(res.json === undefined ? null : JSON.stringify(res.json), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
