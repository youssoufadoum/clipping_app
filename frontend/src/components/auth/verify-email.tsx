"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth/provider";

const RESEND_COOLDOWN = 60;

export function normalizeCode(value: string): string {
  return value.replace(/\D/g, "").slice(0, 10);
}

/** Enter the code emailed by Supabase to confirm a new account. */
export function VerifyEmailForm() {
  const { client } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(params.get("resent") ? "We sent you a new code." : null);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(params.get("resent") ? RESEND_COOLDOWN : 0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  if (!client.requiresEmailVerification) {
    return (
      <Alert variant="warning" title="Email verification is not enabled">
        This server uses the local development sign-in, which doesn&apos;t send emails. Configure Supabase Auth to require verified
        emails. <Link href="/login" className="text-accent underline">Back to sign in</Link>
      </Alert>
    );
  }

  const verify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (code.length < 6) {
      setError("Enter the code from your email.");
      return;
    }
    setBusy(true);
    try {
      await client.verifySignupCode(email.trim(), code);
      router.replace("/onboarding");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setError(null);
    try {
      await client.resendSignupCode(email.trim());
      setNotice("We sent you a new code. Check your inbox and spam folder.");
      setCooldown(RESEND_COOLDOWN);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <form onSubmit={verify} noValidate className="space-y-5">
      <div className="space-y-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Check your email</h1>
        <p className="text-sm text-muted">
          We sent a verification code to <span className="font-medium text-fg">{email || "your email"}</span>. Enter it below to activate
          your account.
        </p>
      </div>
      {!params.get("email") && (
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="code">Verification code</Label>
        <Input
          id="code"
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="123456"
          className="h-12 text-center font-mono text-xl tracking-[0.5em]"
          value={code}
          onChange={(e) => setCode(normalizeCode(e.target.value))}
          autoFocus
        />
      </div>
      {notice && !error && <Alert variant="success">{notice}</Alert>}
      {error && <Alert variant="danger">{error}</Alert>}
      <Button type="submit" className="w-full" loading={busy} disabled={!email.trim()}>
        Verify email
      </Button>
      <div className="flex items-center justify-between text-sm">
        <button type="button" className="text-accent hover:underline disabled:text-muted disabled:no-underline" disabled={cooldown > 0 || !email.trim()} onClick={resend}>
          {cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
        </button>
        <Link href="/login" className="text-muted hover:text-fg">
          Back to sign in
        </Link>
      </div>
    </form>
  );
}
