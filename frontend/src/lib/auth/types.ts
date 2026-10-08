export interface AuthUser {
  id: string;
  email: string | null;
}

export interface SignUpResult {
  /** True when the provider requires the user to confirm their email first. */
  needsEmailConfirmation: boolean;
}

export interface AuthClient {
  readonly mode: "supabase" | "local";
  readonly supportsPasswordReset: boolean;
  readonly supportsOAuth: boolean;
  getUser(): Promise<AuthUser | null>;
  getAccessToken(): Promise<string | null>;
  signIn(email: string, password: string): Promise<void>;
  signUp(email: string, password: string): Promise<SignUpResult>;
  signOut(): Promise<void>;
  signInWithGoogle(): Promise<void>;
  requestPasswordReset(email: string): Promise<void>;
  updatePassword(password: string): Promise<void>;
  onChange(listener: (user: AuthUser | null) => void): () => void;
}
