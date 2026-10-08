"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Spinner } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorMessage } from "@/lib/api";
import { keys, useMe } from "@/lib/queries";
import type { Profile } from "@/lib/types";

export const CREATOR_TYPES = ["Creator", "Podcaster", "Coach", "Educator", "Marketer", "Agency", "Business", "Other"];
export const PLATFORMS = ["TikTok", "YouTube Shorts", "Instagram Reels", "Facebook Reels", "LinkedIn", "Other"];
export const CATEGORIES = ["Business", "Education", "Entertainment", "Gaming", "Health & fitness", "News", "Sports", "Technology", "Lifestyle", "Other"];
export const LANGUAGES = [["en", "English"], ["es", "Spanish"], ["fr", "French"], ["de", "German"], ["pt", "Portuguese"], ["it", "Italian"]] as const;

export function OnboardingView() {
  const me = useMe();
  if (me.isPending) return <div className="p-10"><Spinner /></div>;
  return <OnboardingForm initialName={me.data?.display_name ?? ""} />;
}

function OnboardingForm({ initialName }: { initialName: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [form, setForm] = useState({ display_name: initialName, creator_type: "", main_platform: "", content_category: "", caption_language: "en" });

  const save = useMutation({
    mutationFn: (body: Partial<Profile>) => api<Profile>("/api/v1/me", { method: "PATCH", body }),
    onSuccess: (p) => {
      qc.setQueryData(keys.me, p);
      router.replace("/dashboard");
    },
  });

  const select = (name: keyof typeof form, label: string, options: readonly (string | readonly [string, string])[]) => (
    <div className="space-y-1.5">
      <Label htmlFor={name}>{label}</Label>
      <Select id={name} value={form[name]} onChange={(e) => setForm({ ...form, [name]: e.target.value })}>
        {name !== "caption_language" && <option value="">Choose…</option>}
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
    <div className="mx-auto max-w-lg px-4 py-10">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Welcome to Virello Studio</CardTitle>
          <CardDescription>Tell us a little about your content. Everything here is optional.</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate({
                display_name: form.display_name.trim() || null,
                creator_type: form.creator_type || null,
                main_platform: form.main_platform || null,
                content_category: form.content_category || null,
                caption_language: form.caption_language || null,
                onboarding_completed: true,
              });
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="display_name">Display name</Label>
              <Input id="display_name" maxLength={120} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
            </div>
            {select("creator_type", "What best describes you?", CREATOR_TYPES)}
            {select("main_platform", "Main platform", PLATFORMS)}
            {select("content_category", "Content category", CATEGORIES)}
            {select("caption_language", "Preferred caption language", LANGUAGES)}
            {save.isError && <Alert variant="danger">{errorMessage(save.error)}</Alert>}
            <div className="flex gap-2 pt-2">
              <Button type="submit" loading={save.isPending} className="flex-1">
                Continue
              </Button>
              <Button type="button" variant="ghost" disabled={save.isPending} onClick={() => save.mutate({ onboarding_completed: true })}>
                Skip
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
