import type { Metadata } from "next";

import { PageHero } from "@/components/site/marketing";
import { PricingTable } from "@/components/site/pricing-table";

export const metadata: Metadata = { title: "Pricing" };

export default function PricingPage() {
  return (
    <>
      <PageHero title="Plans for every publishing schedule" description="Start free. Plans differ by monthly minutes, upload size and video length — never by hidden fees." />
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <PricingTable />
      </div>
    </>
  );
}
