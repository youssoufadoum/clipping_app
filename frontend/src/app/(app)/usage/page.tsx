import type { Metadata } from "next";

import { UsageView } from "@/components/app/usage-view";

export const metadata: Metadata = { title: "Usage & credits" };

export default function Page() {
  return <UsageView />;
}
