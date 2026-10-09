"use client";

import { useState } from "react";

import { PageHeader } from "@/components/app/app-shell";
import { LinkImporter } from "@/components/app/link-importer";
import { OrDivider } from "@/components/app/or-divider";
import { Uploader } from "@/components/app/uploader";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function NewProjectView() {
  const [title, setTitle] = useState("");
  return (
    <>
      <PageHeader title="New project" description="Paste a YouTube link or upload a long video. We'll prepare it and, if you like, make AI shorts." />
      <div className="mx-auto grid max-w-3xl gap-6 px-4 py-6 sm:px-8">
        <Card>
          <CardHeader>
            <CardTitle>Project details</CardTitle>
            <CardDescription>Optional — defaults to the file name.</CardDescription>
          </CardHeader>
          <CardContent>
            <Label htmlFor="title">Title</Label>
            <Input id="title" className="mt-1.5" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Podcast episode 42" />
          </CardContent>
        </Card>
        <LinkImporter title={title} />
        <OrDivider />
        <Uploader title={title} />
      </div>
    </>
  );
}
