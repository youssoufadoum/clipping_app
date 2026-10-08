"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { configureApi } from "@/lib/api";
import { LocalAuthClient } from "@/lib/auth/local-client";
import { SupabaseAuthClient } from "@/lib/auth/supabase-client";
import type { AuthClient, AuthUser } from "@/lib/auth/types";
import { config } from "@/lib/config";

type Status = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: Status;
  user: AuthUser | null;
  client: AuthClient;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

let singleton: AuthClient | null = null;
function getClient(): AuthClient {
  singleton ??= config.authMode === "supabase" ? new SupabaseAuthClient() : new LocalAuthClient();
  return singleton;
}

export function AuthProvider({ children, client: injected }: { children: ReactNode; client?: AuthClient }) {
  const client = useMemo(() => injected ?? getClient(), [injected]);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    configureApi(
      () => client.getAccessToken(),
      () => {
        setUser(null);
        setStatus("unauthenticated");
      },
    );
    let active = true;
    client.getUser().then((u) => {
      if (!active) return;
      setUser(u);
      setStatus(u ? "authenticated" : "unauthenticated");
    });
    const unsubscribe = client.onChange((u) => {
      setUser(u);
      setStatus(u ? "authenticated" : "unauthenticated");
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [client]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      client,
      signOut: async () => {
        await client.signOut();
        setUser(null);
        setStatus("unauthenticated");
      },
    }),
    [status, user, client],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
