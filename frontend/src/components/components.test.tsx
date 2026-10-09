import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGuard } from "@/components/app/auth-guard";
import { DashboardView } from "@/components/app/dashboard-view";
import { JobStatusPanel } from "@/components/app/job-status";
import { Uploader } from "@/components/app/uploader";
import { AuthForm } from "@/components/auth/auth-form";
import { RequestResetForm } from "@/components/auth/password-reset";
import { normalizeCode, VerifyEmailForm } from "@/components/auth/verify-email";
import { EmailNotVerifiedError } from "@/lib/auth/types";
import { StatusBadge } from "@/components/status-badge";
import type { Job, Page, Project, Usage } from "@/lib/types";
import { fakeAuthClient, mockFetch, renderWithProviders } from "@/test/utils";

const router = { replace: vi.fn(), push: vi.fn() };
let searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/projects/abc",
  useSearchParams: () => searchParams,
  useParams: () => ({}),
}));

const usage: Usage = {
  plan: {
    code: "free", name: "Free", description: "", monthly_source_minutes: 60, monthly_render_minutes: 30, monthly_ai_minutes: 30,
    max_upload_bytes: 1024, max_video_duration_seconds: 1800, max_projects: 10, watermark: true,
    priority_processing: false, team_workspace: false, checkout_available: false,
  },
  period_start: "2026-10-01T00:00:00Z", period_end: "2026-11-01T00:00:00Z",
  source_minutes_used: 12, source_minutes_limit: 60, source_minutes_remaining: 48,
  render_minutes_used: 3, render_minutes_reserved: 0, render_minutes_limit: 30, render_minutes_remaining: 27,
  ai_minutes_used: 0, ai_minutes_limit: 30, ai_minutes_remaining: 30,
  policy: [],
};

const job = (over: Partial<Job>): Job => ({
  id: "job-1234567890", project_id: "p1", clip_id: null, job_type: "inspect_media", status: "running",
  progress: 0.4, stage: "probing", attempt_count: 1, max_attempts: 3, error_code: null, safe_error_message: null,
  cancel_requested: false, created_at: "", started_at: null, completed_at: null, updated_at: "", ...over,
});

beforeEach(() => {
  router.replace.mockReset();
  router.push.mockReset();
  searchParams = new URLSearchParams();
});
afterEach(() => vi.unstubAllGlobals());

describe("AuthForm", () => {
  it("validates input before calling the provider", async () => {
    const { client } = renderWithProviders(<AuthForm mode="login" />, fakeAuthClient(null));
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(client.signIn).not.toHaveBeenCalled();
  });

  it("signs in and follows a safe next parameter", async () => {
    searchParams = new URLSearchParams({ next: "/projects/42" });
    const { client } = renderWithProviders(<AuthForm mode="login" />, fakeAuthClient(null));
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(client.signIn).toHaveBeenCalledWith("ada@example.com", "correct-horse"));
    expect(router.replace).toHaveBeenCalledWith("/projects/42");
  });

  it("ignores an external next parameter", async () => {
    searchParams = new URLSearchParams({ next: "https://evil.example" });
    renderWithProviders(<AuthForm mode="login" />, fakeAuthClient(null));
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows provider errors", async () => {
    const client = fakeAuthClient(null);
    client.signIn = vi.fn(async () => {
      throw new Error("Incorrect email or password.");
    });
    renderWithProviders(<AuthForm mode="login" />, client);
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Incorrect email or password.")).toBeInTheDocument();
  });
});

describe("AuthGuard", () => {
  it("redirects signed-out users to login with a return path", async () => {
    renderWithProviders(<AuthGuard>secret</AuthGuard>, fakeAuthClient(null));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login?next=%2Fprojects%2Fabc"));
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("renders children for signed-in users", async () => {
    renderWithProviders(<AuthGuard>secret</AuthGuard>);
    expect(await screen.findByText("secret")).toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("labels statuses", () => {
    renderWithProviders(
      <>
        <StatusBadge status="inspecting" />
        <StatusBadge status="failed" />
      </>,
    );
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});

describe("JobStatusPanel", () => {
  it("shows real stage and progress for running jobs", () => {
    renderWithProviders(<JobStatusPanel job={job({})} label="Video processing" invalidate={[]} />);
    expect(screen.getByText(/Reading video details/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
  });

  it("explains failures and retries through the API", async () => {
    const fetch = mockFetch({ "POST /api/v1/jobs/job-1234567890/retry": () => ({ json: job({ status: "queued" }) }) });
    renderWithProviders(
      <JobStatusPanel
        job={job({ status: "failed", error_code: "UNREADABLE_MEDIA", safe_error_message: "The file could not be read as a video." })}
        label="Video processing"
        invalidate={[]}
      />,
    );
    expect(screen.getByText("The file could not be read as a video.")).toBeInTheDocument();
    expect(screen.getByText(/UNREADABLE_MEDIA/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Retry/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const [, init] = fetch.mock.calls[0];
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer test-token");
  });
});

describe("Uploader", () => {
  it("rejects unsupported files without calling the API", async () => {
    const fetch = mockFetch({
      "GET /api/v1/usage": () => ({ json: usage }),
      "GET /api/v1/system/status": () => ({ json: { ai_available: false } }),
    });
    renderWithProviders(<Uploader />);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const input = screen.getByTestId("file-input");
    await userEvent.upload(input, new File(["hello"], "notes.txt", { type: "text/plain" }), { applyAccept: false });
    expect(await screen.findByText(/Unsupported file type/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2); // no project was created
  });

  it("enforces the plan's upload size limit", async () => {
    mockFetch({
      "GET /api/v1/usage": () => ({ json: usage }),
      "GET /api/v1/system/status": () => ({ json: { ai_available: false } }),
    });
    renderWithProviders(<Uploader />);
    expect(await screen.findByText(/up to 1.0 KB/)).toBeInTheDocument();
    await userEvent.upload(screen.getByTestId("file-input"), new File([new Uint8Array(4096)], "big.mp4", { type: "video/mp4" }));
    expect(await screen.findByText(/larger than your plan/)).toBeInTheDocument();
  });
});

describe("DashboardView", () => {
  const emptyPage: Page<Project> = { items: [], total: 0, page: 1, page_size: 12 };

  it("shows an empty state for new users", async () => {
    mockFetch({
      "GET /api/v1/me": () => ({ json: { id: "u1", email: "ada@example.com", display_name: "Ada" } }),
      "GET /api/v1/usage": () => ({ json: usage }),
      "GET /api/v1/projects": () => ({ json: emptyPage }),
    });
    renderWithProviders(<DashboardView />);
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(await screen.findByText("Welcome back, Ada")).toBeInTheDocument();
  });

  it("shows API errors with a retry", async () => {
    mockFetch({
      "GET /api/v1/me": () => ({ json: { id: "u1", email: "ada@example.com" } }),
      "GET /api/v1/usage": () => ({ json: usage }),
      "GET /api/v1/projects": () => ({ status: 503, json: { error: { code: "SERVICE_UNAVAILABLE", message: "Database unavailable." } } }),
    });
    renderWithProviders(<DashboardView />);
    expect(await screen.findByText("Database unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
  });

  it("lists projects with status and clip counts", async () => {
    const project = {
      id: "p1", workspace_id: "w", title: "Podcast 12", status: "ready", source_type: "upload", source_filename: "a.mp4",
      source_size_bytes: 1, source_duration_seconds: 125, source_width: 1920, source_height: 1080, source_fps: 30,
      source_mime_type: "video/mp4", source_metadata: {}, archived_at: null, created_at: "2026-10-01T00:00:00Z",
      updated_at: "", thumbnail_url: null, clip_count: 3, latest_job: null,
    } satisfies Project;
    mockFetch({
      "GET /api/v1/me": () => ({ json: { id: "u1", email: "ada@example.com" } }),
      "GET /api/v1/usage": () => ({ json: usage }),
      "GET /api/v1/projects": () => ({ json: { ...emptyPage, items: [project], total: 1 } }),
    });
    renderWithProviders(<DashboardView />);
    expect(await screen.findByText("Podcast 12")).toBeInTheDocument();
    expect(screen.getByText(/3 clips/)).toBeInTheDocument();
    expect(screen.getByText("2:05")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Podcast 12/ })).toHaveAttribute("href", "/projects/p1");
  });
});

function supabaseLikeClient() {
  const client = fakeAuthClient(null);
  return Object.assign(client, { mode: "supabase" as const, requiresEmailVerification: true, supportsPasswordReset: true });
}

describe("email verification", () => {
  it("sends new sign-ups to the code screen", async () => {
    const client = supabaseLikeClient();
    client.signUp = vi.fn(async () => ({ needsEmailConfirmation: true }));
    renderWithProviders(<AuthForm mode="register" />, client);
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/verify-email?email=ada%40example.com"));
  });

  it("resends a code when an unverified user signs in", async () => {
    const client = supabaseLikeClient();
    client.signIn = vi.fn(async () => {
      throw new EmailNotVerifiedError();
    });
    renderWithProviders(<AuthForm mode="login" />, client);
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(client.resendSignupCode).toHaveBeenCalledWith("ada@example.com"));
    expect(router.push).toHaveBeenCalledWith("/verify-email?email=ada%40example.com&resent=1");
  });

  it("verifies the code and continues to onboarding", async () => {
    searchParams = new URLSearchParams({ email: "ada@example.com" });
    const client = supabaseLikeClient();
    renderWithProviders(<VerifyEmailForm />, client);
    await userEvent.type(screen.getByLabelText("Verification code"), "12 34-56");
    await userEvent.click(screen.getByRole("button", { name: "Verify email" }));
    await waitFor(() => expect(client.verifySignupCode).toHaveBeenCalledWith("ada@example.com", "123456"));
    expect(router.replace).toHaveBeenCalledWith("/onboarding");
  });

  it("shows invalid-code errors and rate-limits resends", async () => {
    searchParams = new URLSearchParams({ email: "ada@example.com" });
    const client = supabaseLikeClient();
    client.verifySignupCode = vi.fn(async () => {
      throw new Error("That code is invalid or has expired. Request a new one.");
    });
    renderWithProviders(<VerifyEmailForm />, client);
    await userEvent.type(screen.getByLabelText("Verification code"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verify email" }));
    expect(await screen.findByText(/invalid or has expired/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Resend code" }));
    expect(client.resendSignupCode).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("button", { name: /Resend code in/ })).toBeDisabled();
  });

  it("explains when verification is not enabled (local dev auth)", () => {
    renderWithProviders(<VerifyEmailForm />, fakeAuthClient(null));
    expect(screen.getByText("Email verification is not enabled")).toBeInTheDocument();
  });

  it("normalizes pasted codes", () => {
    expect(normalizeCode(" 123-456 ")).toBe("123456");
    expect(normalizeCode("12345678901234")).toBe("1234567890");
  });

  it("resets a password with an emailed code", async () => {
    const client = supabaseLikeClient();
    renderWithProviders(<RequestResetForm />, client);
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send reset code" }));
    await waitFor(() => expect(client.requestPasswordReset).toHaveBeenCalledWith("ada@example.com"));
    await userEvent.type(await screen.findByLabelText("Reset code"), "654321");
    await userEvent.type(screen.getByLabelText("New password"), "new-password-1");
    await userEvent.type(screen.getByLabelText("Confirm password"), "new-password-1");
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(client.verifyRecoveryCode).toHaveBeenCalledWith("ada@example.com", "654321"));
    expect(client.updatePassword).toHaveBeenCalledWith("new-password-1");
    expect(router.replace).toHaveBeenCalledWith("/dashboard");
  });
});

describe("AI shorts", () => {
  it("offers 30s / 1 min AI shorts on upload when the server has AI", async () => {
    mockFetch({
      "GET /api/v1/usage": () => ({ json: usage }),
      "GET /api/v1/system/status": () => ({ json: { ai_available: true } }),
    });
    renderWithProviders(<Uploader />);
    const thirty = await screen.findByRole("radio", { name: "30 seconds" });
    expect(thirty).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("radio", { name: "1 minute" }));
    expect(screen.getByRole("radio", { name: "1 minute" })).toHaveAttribute("aria-checked", "true");
  });

  it("hides the AI option when the server has no AI configured", async () => {
    const fetch = mockFetch({
      "GET /api/v1/usage": () => ({ json: usage }),
      "GET /api/v1/system/status": () => ({ json: { ai_available: false } }),
    });
    renderWithProviders(<Uploader />);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("radiogroup", { name: "AI shorts" })).not.toBeInTheDocument();
  });

  it("starts AI analysis with the chosen options", async () => {
    const { AiShortsCard } = await import("@/components/app/ai-panels");
    let sent: unknown = null;
    mockFetch({
      "POST /api/v1/projects/p1/analyze": (body) => {
        sent = body;
        return { json: { id: "j1", status: "queued" } };
      },
    });
    const project = { id: "p1", status: "ready" } as unknown as Project;
    renderWithProviders(<AiShortsCard project={project} aiAvailable />);
    await userEvent.click(screen.getByRole("button", { name: "1 minute" }));
    await userEvent.click(screen.getByRole("button", { name: "2" }));
    await userEvent.click(screen.getByRole("button", { name: /Find viral moments/ }));
    await waitFor(() =>
      expect(sent).toEqual({ target_seconds: 60, count: 2, captions: true, auto_render: true, instructions: null }),
    );
  });
});
