/**
 * Public configuration only. Anything here ships to the browser, so it must
 * never contain secrets — only URLs and the Supabase anon key, which is
 * designed to be public and is constrained by Row Level Security.
 */
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export type AuthMode = "supabase" | "local";

export const config = {
  apiBaseUrl: (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  supabaseUrl,
  supabaseAnonKey,
  authMode: ((process.env.NEXT_PUBLIC_AUTH_MODE as AuthMode | undefined) ??
    (supabaseUrl && supabaseAnonKey ? "supabase" : "local")) as AuthMode,
  googleAuthEnabled: process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED === "true",
  supportEmail: process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "",
};
