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
  /** True when sign-up requires confirming a code sent by email. */
  readonly requiresEmailVerification: boolean;
  verifySignupCode(email: string, code: string): Promise<void>;
  resendSignupCode(email: string): Promise<void>;
  verifyRecoveryCode(email: string, code: string): Promise<void>;
  onChange(listener: (user: AuthUser | null) => void): () => void;
}

/** Thrown by signIn when the account exists but the email has not been verified yet. */
export class EmailNotVerifiedError extends Error {
  constructor() {
    super("Please verify your email address. We can send you a new code.");
    this.name = "EmailNotVerifiedError";
  }
}
