import type { Metadata } from "next";

import { UpdatePasswordForm } from "@/components/auth/password-reset";

export const metadata: Metadata = { title: "Choose a new password" };

export default function UpdatePasswordPage() {
  return <UpdatePasswordForm />;
}
