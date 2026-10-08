import type { Metadata } from "next";

import { RequestResetForm } from "@/components/auth/password-reset";

export const metadata: Metadata = { title: "Reset password" };

export default function ResetPasswordPage() {
  return <RequestResetForm />;
}
