"use client";

import { PageHeader } from "@/components/app/app-shell";
import { PricingTable } from "@/components/site/pricing-table";
import { Alert } from "@/components/ui/feedback";
import { useMe } from "@/lib/queries";

export function BillingView() {
  const me = useMe();
  return (
    <>
      <PageHeader title="Plans & billing" description="Compare plan limits and manage your subscription." />
      <div className="space-y-6 px-4 py-6 sm:px-8">
        <Alert variant="info" title="Online billing isn't available yet">
          You&apos;re on the {me.data ? me.data.plan_code : "…"} plan. Self-serve upgrades through Stripe are coming; plan limits below are
          enforced today.
        </Alert>
        <PricingTable currentPlan={me.data?.plan_code} />
      </div>
    </>
  );
}
