import { api } from "@/lib/api";
import type { AuthClient, AuthUser, SignUpResult } from "@/lib/auth/types";

const STORAGE_KEY = "virello.local-session";

interface StoredSession {
  token: string;
  user: AuthUser;
  expiresAt: number;
}

interface TokenResponse {
  access_token: string;
  expires_in: number;
  user_id: string;
  email: string;
}

/**
 * Development-only provider backed by the API's AUTH_MODE=local endpoints.
 * The API refuses these endpoints in production; this exists so the full app
 * can be exercised without a Supabase project.
 */
export class LocalAuthClient implements AuthClient {
  readonly mode = "local" as const;
  readonly supportsPasswordReset = false;
  readonly supportsOAuth = false;
  readonly requiresEmailVerification = false;
  private listeners = new Set<(user: AuthUser | null) => void>();

  private read(): StoredSession | null {
    if (typeof window === "undefined") return null;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const session = JSON.parse(raw) as StoredSession;
      if (session.expiresAt <= Date.now() + 30_000) {
        window.localStorage.removeItem(STORAGE_KEY);
        return null;
      }
      return session;
    } catch {
      return null;
    }
  }

  private write(res: TokenResponse): void {
    const session: StoredSession = {
      token: res.access_token,
      user: { id: res.user_id, email: res.email },
      expiresAt: Date.now() + res.expires_in * 1000,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    this.listeners.forEach((l) => l(session.user));
  }

  async getUser(): Promise<AuthUser | null> {
    return this.read()?.user ?? null;
  }

  async getAccessToken(): Promise<string | null> {
    return this.read()?.token ?? null;
  }

  async signIn(email: string, password: string): Promise<void> {
    this.write(await api<TokenResponse>("/api/v1/auth/local/login", { body: { email, password }, auth: false }));
  }

  async signUp(email: string, password: string): Promise<SignUpResult> {
    this.write(await api<TokenResponse>("/api/v1/auth/local/register", { body: { email, password }, auth: false }));
    return { needsEmailConfirmation: false };
  }

  async signOut(): Promise<void> {
    window.localStorage.removeItem(STORAGE_KEY);
    this.listeners.forEach((l) => l(null));
  }

  async signInWithGoogle(): Promise<void> {
    throw new Error("Google sign-in is not available in local development mode.");
  }

  async requestPasswordReset(): Promise<void> {
    throw new Error("Password reset emails are not available in local development mode.");
  }

  async updatePassword(): Promise<void> {
    throw new Error("Password changes are not available in local development mode.");
  }

  async verifySignupCode(): Promise<void> {
    throw new Error("Email verification requires Supabase Auth.");
  }

  async resendSignupCode(): Promise<void> {
    throw new Error("Email verification requires Supabase Auth.");
  }

  async verifyRecoveryCode(): Promise<void> {
    throw new Error("Password reset requires Supabase Auth.");
  }

  onChange(listener: (user: AuthUser | null) => void): () => void {
    this.listeners.add(listener);
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) listener(this.read()?.user ?? null);
    };
    window.addEventListener("storage", onStorage);
    return () => {
      this.listeners.delete(listener);
      window.removeEventListener("storage", onStorage);
    };
  }
}
