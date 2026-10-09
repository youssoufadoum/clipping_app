"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { FieldError, Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth/provider";

const requestSchema = z.object({ email: z.string().trim().email("Enter a valid email address.") });
const updateSchema = z
  .object({
    password: z.string().min(8, "Use at least 8 characters.").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { message: "Passwords do not match.", path: ["confirm"] });

const codeResetSchema = z
  .object({
    code: z.string().regex(/^\d{6,10}$/, "Enter the code from your email."),
    password: z.string().min(8, "Use at least 8 characters.").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { message: "Passwords do not match.", path: ["confirm"] });

export function RequestResetForm() {
  const { client } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof requestSchema>>({ resolver: zodResolver(requestSchema) });
  const codeForm = useForm<z.infer<typeof codeResetSchema>>({ resolver: zodResolver(codeResetSchema) });

  if (!client.supportsPasswordReset) {
    return (
      <Alert variant="warning" title="Password reset unavailable">
        Password reset emails require Supabase Auth, which is not configured on this server.{" "}
        <Link href="/login" className="text-accent underline">Back to sign in</Link>
      </Alert>
    );
  }

  if (email) {
    return (
      <form
        noValidate
        className="space-y-4"
        onSubmit={codeForm.handleSubmit(async ({ code, password }) => {
          setError(null);
          try {
            await client.verifyRecoveryCode(email, code);
            await client.updatePassword(password);
            router.replace("/dashboard");
          } catch (e) {
            setError(errorMessage(e));
          }
        })}
      >
        <h1 className="text-center text-2xl font-semibold">Enter your code</h1>
        <p className="text-center text-sm text-muted">
          If an account exists for <span className="font-medium text-fg">{email}</span>, we emailed it a reset code.
        </p>
        <div className="space-y-1.5">
          <Label htmlFor="code">Reset code</Label>
          <Input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            className="h-12 text-center font-mono text-xl tracking-[0.5em]"
            {...codeForm.register("code", { setValueAs: (v: string) => v.replace(/\D/g, "") })}
          />
          <FieldError message={codeForm.formState.errors.code?.message} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">New password</Label>
          <Input id="password" type="password" autoComplete="new-password" {...codeForm.register("password")} />
          <FieldError message={codeForm.formState.errors.password?.message} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="confirm">Confirm password</Label>
          <Input id="confirm" type="password" autoComplete="new-password" {...codeForm.register("confirm")} />
          <FieldError message={codeForm.formState.errors.confirm?.message} />
        </div>
        {error && <Alert variant="danger">{error}</Alert>}
        <Button type="submit" className="w-full" loading={codeForm.formState.isSubmitting}>
          Reset password
        </Button>
        <p className="text-center text-sm">
          <button type="button" className="text-accent hover:underline" onClick={() => setEmail(null)}>
            Use a different email
          </button>
        </p>
      </form>
    );
  }
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={form.handleSubmit(async ({ email: address }) => {
        setError(null);
        try {
          await client.requestPasswordReset(address);
          setEmail(address);
        } catch (e) {
          setError(errorMessage(e));
        }
      })}
    >
      <h1 className="text-center text-2xl font-semibold">Reset your password</h1>
      <p className="text-center text-sm text-muted">Enter your email and we&apos;ll send you a reset code.</p>
      <div className="space-y-1.5">
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" autoComplete="email" aria-invalid={!!form.formState.errors.email} {...form.register("email")} />
        <FieldError message={form.formState.errors.email?.message} />
      </div>
      {error && <Alert variant="danger">{error}</Alert>}
      <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
        Send reset code
      </Button>
      <p className="text-center text-sm">
        <Link href="/login" className="text-accent hover:underline">Back to sign in</Link>
      </p>
    </form>
  );
}

export function UpdatePasswordForm() {
  const { client, status } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof updateSchema>>({ resolver: zodResolver(updateSchema) });

  if (status === "unauthenticated") {
    return (
      <Alert variant="danger" title="Reset link invalid or expired">
        <Link href="/reset-password" className="text-accent underline">Request a new link</Link>
      </Alert>
    );
  }
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={form.handleSubmit(async ({ password }) => {
        setError(null);
        try {
          await client.updatePassword(password);
          router.replace("/dashboard");
        } catch (e) {
          setError(errorMessage(e));
        }
      })}
    >
      <h1 className="text-center text-2xl font-semibold">Choose a new password</h1>
      <div className="space-y-1.5">
        <Label htmlFor="password">New password</Label>
        <Input id="password" type="password" autoComplete="new-password" {...form.register("password")} />
        <FieldError message={form.formState.errors.password?.message} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="confirm">Confirm password</Label>
        <Input id="confirm" type="password" autoComplete="new-password" {...form.register("confirm")} />
        <FieldError message={form.formState.errors.confirm?.message} />
      </div>
      {error && <Alert variant="danger">{error}</Alert>}
      <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
        Update password
      </Button>
    </form>
  );
}
