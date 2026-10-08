"use client";

import { Link2 } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/app/app-shell";
import { Uploader } from "@/components/app/uploader";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function NewProjectView() {
  const [title, setTitle] = useState("");
  return (
    <>
      <PageHeader title="New project" description="Upload a long video. We'll store it privately and prepare it for editing." />
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
        <Uploader title={title} />
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Link2 className="size-4" aria-hidden /> Import from a link
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Alert variant="info" title="Not available">
              Link import isn&apos;t supported. Many platforms don&apos;t allow downloads through third-party tools, so please upload a
              file you have the rights to use.
            </Alert>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
