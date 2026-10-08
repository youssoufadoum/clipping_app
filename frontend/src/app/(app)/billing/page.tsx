import type { Metadata } from "next";

import { BillingView } from "@/components/app/billing-view";

export const metadata: Metadata = { title: "Plans & billing" };

export default function Page() {
  return <BillingView />;
}
