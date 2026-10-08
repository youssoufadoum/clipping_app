import type { Metadata } from "next";

import { ExportsView } from "@/components/app/exports-view";

export const metadata: Metadata = { title: "Exports" };

export default function Page() {
  return <ExportsView />;
}
