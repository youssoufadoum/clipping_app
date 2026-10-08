import { Suspense } from "react";

import { ProjectView } from "@/components/app/project-view";
import { Spinner } from "@/components/ui/feedback";

export default function ProjectPage() {
  return (
    <Suspense fallback={<div className="p-8"><Spinner /></div>}>
      <ProjectView />
    </Suspense>
  );
}
