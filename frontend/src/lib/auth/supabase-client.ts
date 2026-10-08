import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { config } from "@/lib/config";
import type { AuthClient, AuthUser, SignUpResult } from "@/lib/auth/types";

/** Supabase Auth: email/password with verification, password reset, optional Google OAuth. */
export class SupabaseAuthClient implements AuthClient {
  readonly mode = "supabase" as const;
  readonly supportsPasswordReset = true;
  readonly supportsOAuth = config.googleAuthEnabled;
  private client: SupabaseClient;

  constructor() {
    this.client = createClient(config.supabaseUrl, config.supabaseAnonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: "pkce" },
    });
  }

  private origin(): string {
    return typeof window === "undefined" ? "" : window.location.origin;
  }

  async getUser(): Promise<AuthUser | null> {
    const { data } = await this.client.auth.getSession();
    const user = data.session?.user;
    return user ? { id: user.id, email: user.email ?? null } : null;
  }

  async getAccessToken(): Promise<string | null> {
    // getSession refreshes an expiring token automatically.
    const { data } = await this.client.auth.getSession();
    return data.session?.access_token ?? null;
  }

  async signIn(email: string, password: string): Promise<void> {
    const { error } = await this.client.auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
  }

  async signUp(email: string, password: string): Promise<SignUpResult> {
    const { data, error } = await this.client.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${this.origin()}/auth/callback` },
    });
    if (error) throw new Error(error.message);
    return { needsEmailConfirmation: !data.session };
  }

  async signOut(): Promise<void> {
    await this.client.auth.signOut();
  }

  async signInWithGoogle(): Promise<void> {
    const { error } = await this.client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${this.origin()}/auth/callback` },
    });
    if (error) throw new Error(error.message);
  }

  async requestPasswordReset(email: string): Promise<void> {
    const { error } = await this.client.auth.resetPasswordForEmail(email, {
      redirectTo: `${this.origin()}/auth/callback?next=/reset-password/update`,
    });
    if (error) throw new Error(error.message);
  }

  async updatePassword(password: string): Promise<void> {
    const { error } = await this.client.auth.updateUser({ password });
    if (error) throw new Error(error.message);
  }

  onChange(listener: (user: AuthUser | null) => void): () => void {
    const { data } = this.client.auth.onAuthStateChange((_event, session) => {
      const user = session?.user;
      listener(user ? { id: user.id, email: user.email ?? null } : null);
    });
    return () => data.subscription.unsubscribe();
  }
}
