import { Suspense } from "react";

import { ClipEditor } from "@/components/editor/clip-editor";
import { Spinner } from "@/components/ui/feedback";

export default function ClipEditorPage() {
  return (
    <Suspense fallback={<div className="p-8"><Spinner label="Loading editor" /></div>}>
      <ClipEditor />
    </Suspense>
  );
}
