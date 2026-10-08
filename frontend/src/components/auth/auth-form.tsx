"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { FieldError, Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth/provider";
import { safeNext } from "@/lib/redirect";

export const credentialsSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(8, "Use at least 8 characters.").max(128, "Use at most 128 characters."),
});
type Credentials = z.infer<typeof credentialsSchema>;

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { client } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [serverError, setServerError] = useState<string | null>(null);
  const [checkEmail, setCheckEmail] = useState(false);
  const form = useForm<Credentials>({ resolver: zodResolver(credentialsSchema), defaultValues: { email: "", password: "" } });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async ({ email, password }) => {
    setServerError(null);
    try {
      if (mode === "login") {
        await client.signIn(email, password);
        router.replace(next);
      } else {
        const res = await client.signUp(email, password);
        if (res.needsEmailConfirmation) setCheckEmail(true);
        else router.replace("/onboarding");
      }
    } catch (err) {
      setServerError(errorMessage(err));
    }
  });

  if (checkEmail) {
    return (
      <Alert variant="success" title="Check your inbox">
        We sent a confirmation link to {form.getValues("email")}. Open it to activate your account, then sign in.
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p className="text-sm text-muted">
          {mode === "login" ? "Sign in to continue to your projects." : "Start turning long videos into shorts."}
        </p>
      </div>

      {client.mode === "local" && (
        <Alert variant="warning" title="Local development sign-in">
          This server uses the development auth provider. Configure Supabase for production.
        </Alert>
      )}

      {client.supportsOAuth && (
        <>
          <Button
            type="button"
            variant="secondary"
            className="w-full"
            onClick={() => client.signInWithGoogle().catch((e) => setServerError(errorMessage(e)))}
          >
            Continue with Google
          </Button>
          <div className="flex items-center gap-3 text-xs text-muted">
            <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
          </div>
        </>
      )}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} aria-describedby="email-error" {...form.register("email")} />
          <FieldError id="email-error" message={errors.email?.message} />
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            {mode === "login" && client.supportsPasswordReset && (
              <Link href="/reset-password" className="text-xs text-accent hover:underline">
                Forgot password?
              </Link>
            )}
          </div>
          <Input
            id="password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            aria-invalid={!!errors.password}
            aria-describedby="password-error"
            {...form.register("password")}
          />
          <FieldError id="password-error" message={errors.password?.message} />
        </div>
        {serverError && <Alert variant="danger">{serverError}</Alert>}
        <Button type="submit" className="w-full" loading={isSubmitting}>
          {mode === "login" ? "Sign in" : "Create account"}
        </Button>
      </form>

      <p className="text-center text-sm text-muted">
        {mode === "login" ? (
          <>
            New to Virello? <Link href="/register" className="text-accent hover:underline">Create an account</Link>
          </>
        ) : (
          <>
            Already have an account? <Link href="/login" className="text-accent hover:underline">Sign in</Link>
          </>
        )}
      </p>
      {mode === "register" && (
        <p className="text-center text-xs text-muted">
          By creating an account you agree to the <Link href="/terms" className="underline">Terms</Link> and{" "}
          <Link href="/privacy" className="underline">Privacy policy</Link>.
        </p>
      )}
    </div>
  );
}
