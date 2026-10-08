"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/app/app-shell";
import { CATEGORIES, CREATOR_TYPES, LANGUAGES, PLATFORMS } from "@/components/app/onboarding-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Alert, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth/provider";
import { keys, useMe } from "@/lib/queries";
import type { Profile } from "@/lib/types";

function DeleteAccount() {
  const { signOut } = useAuth();
  const router = useRouter();
  const [confirm, setConfirm] = useState("");
  const del = useMutation({
    mutationFn: () => api<void>("/api/v1/me", { method: "DELETE", body: { confirm: "DELETE" } }),
    onSuccess: async () => {
      await signOut();
      router.replace("/");
    },
  });
  return (
    <Dialog onOpenChange={() => setConfirm("")}>
      <DialogTrigger asChild>
        <Button variant="danger">Delete account</Button>
      </DialogTrigger>
      <DialogContent title="Delete your account?" description="All projects, videos, clips and exports are permanently deleted. This cannot be undone.">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (confirm === "DELETE") del.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="confirm-delete">Type DELETE to confirm</Label>
            <Input id="confirm-delete" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
          </div>
          {del.isError && <Alert variant="danger">{errorMessage(del.error)}</Alert>}
          <Button type="submit" variant="danger" className="w-full" disabled={confirm !== "DELETE"} loading={del.isPending}>
            Permanently delete account
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ProfileForm({ profile }: { profile: Profile }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState<Partial<Profile>>(profile);

  const save = useMutation({
    mutationFn: () =>
      api<Profile>("/api/v1/me", {
        method: "PATCH",
        body: {
          display_name: form.display_name?.trim() || null,
          creator_type: form.creator_type || null,
          main_platform: form.main_platform || null,
          content_category: form.content_category || null,
          caption_language: form.caption_language || null,
        },
      }),
    onSuccess: (p) => {
      qc.setQueryData(keys.me, p);
      toast("Profile saved");
    },
  });

  const field = (name: keyof Profile, label: string, options: readonly (string | readonly [string, string])[]) => (
    <div className="space-y-1.5">
      <Label htmlFor={name}>{label}</Label>
      <Select id={name} value={(form[name] as string) ?? ""} onChange={(e) => setForm({ ...form, [name]: e.target.value })}>
        <option value="">Not set</option>
        {options.map((o) => {
          const [value, text] = typeof o === "string" ? [o.toLowerCase(), o] : o;
          return (
            <option key={value} value={value}>
              {text}
            </option>
          );
        })}
      </Select>
    </div>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Signed in as {profile.email}</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="display_name">Display name</Label>
            <Input id="display_name" maxLength={120} value={form.display_name ?? ""} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </div>
          {field("creator_type", "Role", CREATOR_TYPES)}
          {field("main_platform", "Main platform", PLATFORMS)}
          {field("content_category", "Content category", CATEGORIES)}
          {field("caption_language", "Caption language", LANGUAGES)}
          {save.isError && (
            <Alert variant="danger" className="sm:col-span-2">
              {errorMessage(save.error)}
            </Alert>
          )}
          <div className="sm:col-span-2">
            <Button type="submit" loading={save.isPending}>
              Save profile
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function SettingsView() {
  const me = useMe();
  const { client } = useAuth();
  return (
    <>
      <PageHeader title="Settings" description="Manage your profile and account." />
      <div className="mx-auto max-w-2xl space-y-6 px-4 py-6 sm:px-8">
        {me.isPending ? (
          <Skeleton className="h-80" />
        ) : me.isError ? (
          <ErrorState message={errorMessage(me.error)} onRetry={() => me.refetch()} />
        ) : (
          <ProfileForm key={me.data.id} profile={me.data} />
        )}

        <Card>
          <CardHeader>
            <CardTitle>Sign-in</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted">
            {client.mode === "supabase"
              ? "Password changes and email verification are handled by Supabase Auth. Use “Forgot password” on the sign-in page to set a new password."
              : "This server uses the local development auth provider. Password changes are not available."}
          </CardContent>
        </Card>

        <Card className="border-danger/40">
          <CardHeader>
            <CardTitle>Delete account</CardTitle>
            <CardDescription>Permanently remove your account and all stored media.</CardDescription>
          </CardHeader>
          <CardContent>
            <DeleteAccount />
          </CardContent>
        </Card>
      </div>
    </>
  );
}
