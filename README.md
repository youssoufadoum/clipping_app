# Virello Studio

**Turn long videos into scroll-stopping shorts.**

Virello Studio is an AI video repurposing SaaS: upload a long video, cut it into
clips, reframe them for TikTok / Shorts / Reels / LinkedIn, and export
platform-ready MP4s. This repository holds the full stack:

| Path | What |
| --- | --- |
| `frontend/` | Next.js 16 (App Router, React 19, TypeScript strict, Tailwind v4) — marketing site, auth, dashboard, editor |
| `backend/` | FastAPI API, SQLAlchemy 2 + Alembic, Celery worker with FFmpeg/FFprobe |
| `docs/` | API reference and the generated OpenAPI spec |
| `docker-compose.yml` | Local full stack (Postgres, Redis, API, worker, beat, web) |

---

## Build status

The build follows the phased plan in the product brief. **Phase 1 (functional
foundation) is complete.** Anything not listed as done is **not implemented**,
and the app labels it "In development" or returns an explicit
`503 FEATURE_UNAVAILABLE` instead of faking it.

### Phase 1 — functional foundation ✅
- [x] Project structure, design system (light marketing / dark workspace tokens), original logo
- [x] Marketing site: home, features, how it works, use cases, pricing, FAQ, contact, help, privacy, terms, cookies
- [x] Auth: Supabase Auth (email/password, verification, password reset, optional Google OAuth), plus a
      **development-only** local provider that the API refuses when `APP_ENV=production`
- [x] Server-side JWT verification on every protected request (JWKS or legacy HS256); onboarding; profile; account deletion
- [x] PostgreSQL schema for all 15 tables in the brief + `audit_events` + `local_auth_users`, with Alembic migrations
- [x] Row Level Security on every table, with read-only `auth.uid()` policies on Supabase (verified against a simulated `auth` schema)
- [x] Dashboard: search, status filter, pagination, thumbnails, status, clip counts, usage, empty/error states
- [x] Project actions: create, rename, open, archive/restore, delete (removes media), retry failed processing, job history
- [x] Direct-to-storage uploads using short-lived signed URLs (S3/R2/MinIO, or local signed URLs); real progress, cancel, retry
- [x] Server-side upload verification: size check, magic-byte content sniffing, FFprobe inspection, rotation-aware dimensions
- [x] Durable Celery/Redis queue: idempotent job claiming, retries with exponential backoff, cancellation, timeouts,
      stale-job recovery (beat), queue-outage handling
- [x] Real job status: stages and progress come from the worker (FFmpeg `-progress`), polled only while work is active
- [x] FFmpeg clip rendering: accurate trims, 9:16 / 1:1 / 16:9 / original, adjustable crop position, padded fit,
      optional EBU R128 loudness normalization, H.264/AAC fast-start MP4, output validation with FFprobe, thumbnails
- [x] Trim editor: source preview with live crop overlay, draggable timeline, timecode inputs, set-at-playhead, loop,
      undo/redo, keyboard shortcuts, save, render, preview and download of the real output
- [x] Plans + quotas enforced on the server (upload size, duration, monthly source/render minutes, project count),
      usage ledger with idempotent charging, reservations for queued renders, free-plan watermark
- [x] Exports history, usage page with the charging policy, billing page (plan limits; checkout honestly unavailable)
- [x] Health (`/health`), readiness (`/ready`), token-protected metrics (`/metrics`), structured JSON logs with
      correlation IDs and secret redaction, optional Sentry
- [x] Tests: 145 backend (real Postgres + FFmpeg; AI via mocked HTTP and a fake provider), 42 frontend
      (Vitest/Testing Library), plus Playwright browser E2E runs
- [x] Dockerfiles (API, worker, web), docker-compose, CI workflow, `.env.example` files

### Phase 2 — AI shorts ✅ (needs `GEMINI_API_KEY`)
- [x] One-click **AI shorts**: choose 30 seconds or 1 minute at upload (or later on the project page)
- [x] Google Gemini provider (REST, server-side key) for transcription and moment picking, with structured JSON output,
      retries/backoff, safe error mapping (bad key, rate limit, blocked, malformed output)
- [x] Chunked transcription (10-minute audio chunks extracted with FFmpeg) so long videos fit model limits
- [x] The model picks **segment ranges**, so clips always start/end on real sentence boundaries; durations are fitted to the
      target, validated against the media, ranked, and near-duplicates are dropped
- [x] AI clips store title, reason and an engagement *estimate* (labeled as not a guarantee); optional creator instructions
- [x] Editable transcript; captions burned into renders (lower third or center) and SRT/VTT downloads
- [x] AI minutes quota and usage ledger; failed AI jobs are not charged and leave the project usable
- [ ] Word-level timestamps (Gemini returns phrase-level timing; caption timing within a phrase is approximated)
- [x] **Paste a YouTube link** instead of uploading (yt-dlp), with rights confirmation, an on/off switch, link
      validation, pre-download length/quota checks, real download progress, cancel and retry (see the caveats below)

### Accounts — real email verification ✅ (needs Supabase)
- [x] Sign-up requires a **6-digit code emailed by Supabase**; unverified sign-ins get a fresh code and the code screen
- [x] Resend with cooldown; password reset by emailed code; the API rejects tokens whose email isn't verified
- [x] The user's verified email is stored on their profile from the verified token

### Phase 3 — editing & SaaS
- [ ] Stripe checkout, portal and verified idempotent webhooks (`subscriptions`, `webhook_events` tables exist)
- [ ] Resend transactional email (welcome, job completion/failure)
- [ ] Brand templates UI, admin area (server-side `is_admin` + `admin_user` dependency exist), media retention enforcement

### Phase 4 — advanced
- [ ] Subject-aware reframing, translation, audio enhancement, B-roll, voice-over, social publishing, teams, public API

---

## Architecture

```
Browser ──(Supabase JS: sign in)──▶ Supabase Auth
   │
   ├──(Bearer JWT)──▶ FastAPI /api/v1 ──▶ PostgreSQL (Supabase)
   │                       │  └──▶ Redis ──▶ Celery worker ──▶ FFmpeg / FFprobe
   │                       │                       │
   └──(presigned PUT/GET)──┴───────────────────────┴──▶ S3-compatible storage (private)
```

- The browser never receives service keys. It holds only the Supabase anon key (public by design, constrained by RLS)
  and short-lived signed URLs.
- Large files go **directly to object storage** with presigned PUTs; they never pass through Next.js or FastAPI.
- The worker reads sources over signed HTTPS range requests, so cutting a 30 s clip from a multi-GB file doesn't
  download the whole file.
- Every FFmpeg command is an argument list run without a shell. Only validated numbers and server-generated paths
  reach filter graphs; titles and other free text never do.
- Provider abstractions: `StorageProvider` (S3, local), auth verification (Supabase, local-dev). The AI, billing,
  notification and publishing interfaces arrive with their phases.

### Job lifecycle
`queued → running → succeeded | failed | cancelled` (validated transitions). The worker claims a job with a row lock,
so duplicate deliveries are harmless. Retryable failures re-queue with backoff (15 s, 30 s, …) up to `max_attempts`.
A beat task re-dispatches queued jobs that never started and recovers jobs orphaned by a crashed worker.
Projects follow `draft → uploading → queued → inspecting → ready` (plus `failed`, `cancelled`, `archived`, and the
statuses reserved for later phases).

### Usage policy (shown to users)
- Source minutes are counted once per project when its video is processed successfully.
- Render minutes are counted per successful export, based on clip length.
- Failed, cancelled and rejected jobs are never charged; queued and running renders are reserved.
- Usage is metered in tenths of a minute (rounded up) and resets monthly (UTC).

---

## Local development

### Prerequisites
Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+, PostgreSQL 16, Redis 7, FFmpeg 6+ (with libx264, libass,
freetype).

### 1. Backend
```bash
cd backend
cp .env.example .env
# For a no-cloud setup set: AUTH_MODE=local, STORAGE_BACKEND=local, APP_ENV=development
uv sync
createdb virello                       # or point DATABASE_URL at Supabase
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```
In two more terminals:
```bash
uv run celery -A app.worker.celery_app worker -Q media --concurrency 2 --loglevel INFO
uv run celery -A app.worker.celery_app beat --loglevel INFO     # stale-job recovery
```
API docs: http://localhost:8000/api/docs · readiness: http://localhost:8000/ready

### 2. Frontend
```bash
cd frontend
cp .env.example .env.local     # leave Supabase blank to use the local dev auth provider
npm install
npm run dev                     # http://localhost:3000
```

### Docker Compose (alternative)
```bash
cp .env.example .env      # optional: add Supabase and Gemini keys
docker compose up --build
```
Runs Postgres, Redis, API (migrates on start), worker, beat and web with a shared media volume. Without keys it uses
the dev-only local sign-in and AI is off.

### Changing a user's plan (until Stripe ships)
```bash
cd backend && uv run python -m app.cli set-plan user@example.com creator
```

---

## Configuration

All secrets come from environment variables. See `backend/.env.example` and `frontend/.env.example`; both contain
placeholders only. Never commit populated `.env` files (they are git-ignored).

### Real accounts with email verification codes (Supabase)
Without Supabase the app uses a development-only sign-in that accepts any email and sends nothing. To require
real, verified emails:

1. Create a free project at https://supabase.com.
2. **Authentication → Sign In / Providers → Email:** turn on **Confirm email**.
3. **Authentication → Emails → Templates:** edit **Confirm signup** so the email shows the code, e.g.
   `<p>Your Virello Studio verification code is <strong>{{ .Token }}</strong></p>`.
   Do the same for **Reset Password** (`{{ .Token }}`). The app's code screens use these codes.
4. **Authentication → Emails → SMTP Settings:** add your own SMTP server. Supabase's built-in sender only delivers
   to your project's team members and is heavily rate-limited, so real users won't get codes without this.
   Any SMTP provider works (for example Resend: host `smtp.resend.com`, port `465`, user `resend`,
   password = your Resend API key, with a verified sending domain).
5. **Authentication → URL Configuration:** set the Site URL to your frontend (e.g. `http://localhost:3000`) and add
   `http://localhost:3000/auth/callback` to the redirect URLs.
6. **Project Settings → API Keys:** copy the project URL, the anon/publishable key and the service_role/secret key.
   With Docker Compose, put them in the root `.env` (see `.env.example`) with `AUTH_MODE=supabase`, then rebuild:
   `docker compose up --build`.

### AI shorts (Google Gemini)
1. Create an API key at https://aistudio.google.com/apikey.
2. Set `GEMINI_API_KEY` (root `.env` for Docker Compose, or `backend/.env`). Optional: `GEMINI_MODEL`
   (default `gemini-2.5-flash`).
3. Restart. The dashboard then shows **AI shorts: Off / 30 seconds / 1 minute**.

The video's audio (and then its transcript) is sent to Google's Gemini API under Google's API terms. Each video is
transcribed once; re-running AI reuses the saved transcript.

### YouTube link import
Users can paste a YouTube link instead of uploading a file. The worker downloads the video with
[yt-dlp](https://github.com/yt-dlp/yt-dlp), which needs a JavaScript runtime: the `deno` Python package installs one
automatically. Processing then continues exactly like an upload (inspection, then AI shorts if chosen).

Read this before enabling it publicly:
- **YouTube's Terms of Service restrict downloading.** Users must tick "I own this video or have permission"
  (recorded in `audit_events`), but the legal risk is the operator's. Turn the feature off with
  `YOUTUBE_IMPORT_ENABLED=false`.
- **YouTube often blocks cloud/datacenter servers** ("Sign in to confirm you're not a bot"). It usually works from a
  home connection; on a hosted server it may fail, and users then see a message suggesting they upload the file.
- Only single-video links are accepted (`youtube.com/watch?v=`, `youtu.be/`, `/shorts/`, `/live/`, `/embed/`). The
  pasted URL is never fetched: the video id is validated and a canonical youtube.com URL is rebuilt, so other hosts
  can't be reached. Playlists, live streams, private, age-restricted and members-only videos are refused.
- Length and plan limits are checked **before** downloading; downloads are capped at 1080p and your plan's size limit.
- yt-dlp must stay current as YouTube changes: rebuild images regularly (`docker compose build --no-cache`).

### Supabase (details)
1. Create a project. In **Project Settings → API**, copy the URL and anon key into `NEXT_PUBLIC_SUPABASE_URL` /
   `NEXT_PUBLIC_SUPABASE_ANON_KEY` (frontend) and `SUPABASE_URL` / `SUPABASE_ANON_KEY` (backend). Put the
   service-role key in `SUPABASE_SERVICE_ROLE_KEY` (**backend only**; used to delete auth users on account deletion).
2. Set `AUTH_MODE=supabase`. Tokens are verified with the project's JWKS
   (`$SUPABASE_URL/auth/v1/.well-known/jwks.json`). Legacy HS256 projects set `SUPABASE_JWT_SECRET` instead.
3. Use the Supabase Postgres connection string as `DATABASE_URL`
   (`postgresql+psycopg://postgres:<password>@<host>:5432/postgres`), then run `alembic upgrade head`. The RLS
   migration detects the `auth` schema and creates the `auth.uid()` policies.
4. In **Authentication → URL Configuration**, set the Site URL to your frontend and add
   `https://<frontend>/auth/callback` to the redirect URLs. Email confirmation and password reset links land there.
5. Optional Google sign-in: enable the Google provider in Supabase, then set `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true`.

### Object storage (S3 / Cloudflare R2 / MinIO)
1. Create a **private** bucket and an access key limited to that bucket.
2. Set `STORAGE_BACKEND=s3`, `S3_BUCKET_NAME`, `S3_REGION` (`auto` for R2), `S3_ENDPOINT_URL` (R2:
   `https://<account>.r2.cloudflarestorage.com`), `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`.
3. Allow browser uploads and playback with a bucket CORS rule:
   ```json
   [{ "AllowedOrigins": ["https://app.example.com"], "AllowedMethods": ["PUT", "GET", "HEAD"],
      "AllowedHeaders": ["Content-Type", "Range"], "ExposeHeaders": ["ETag", "Content-Length", "Content-Range"],
      "MaxAgeSeconds": 3600 }]
   ```
4. Add the storage origin to `NEXT_PUBLIC_STORAGE_ORIGINS` so the Content Security Policy permits it.
5. Recommended: a lifecycle rule that aborts incomplete multipart uploads after 1 day.

`STORAGE_BACKEND=local` serves HMAC-signed URLs from the API itself. It only works when the API and worker share a
filesystem (one machine, or the Compose volume). Don't use it for multi-node production.

### Not yet used
`OPENAI_*`, `STRIPE_*`, `RESEND_API_KEY` and `EMAIL_FROM` are reserved for later phases (verification emails are sent
by Supabase, not the backend). Setting them has no effect today. `MEDIA_RETENTION_DAYS` is not enforced yet.

---

## Testing

```bash
# Backend: needs PostgreSQL (TEST_DATABASE_URL, default .../virello_test) and FFmpeg. Redis not required.
cd backend && uv run ruff check . && uv run mypy app && uv run pytest

# Frontend
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

Backend tests run the real pipeline: they generate synthetic test videos with FFmpeg's `testsrc2`/`sine` sources,
upload them through the signed-URL flow, run inspection and rendering in-process through the real task functions,
and validate outputs with FFprobe. They also cover authorization (cross-user access returns 404 on every resource),
quota enforcement, idempotency, retries, recovery, signed-URL tampering/expiry, and JWT verification. External paid
APIs are never called.

---

## Deployment

| Component | Suggested host | Notes |
| --- | --- | --- |
| Web (`frontend/`) | Vercel | Set the `NEXT_PUBLIC_*` variables at build time. `frontend/Dockerfile` for container hosts. |
| API (`backend/Dockerfile`, target `api`) | Fly.io, Render, Railway, Cloud Run, ECS | Run `alembic upgrade head` as a release step. Health check `/health`, readiness `/ready`. |
| Worker (`backend/Dockerfile.worker`) | Any container host with enough CPU/RAM/disk for FFmpeg | Scale horizontally; concurrency per container = `MAX_RENDER_CONCURRENCY`. |
| Beat (same image, `celery … beat`) | Exactly **one** instance | Runs stale-job recovery every 60 s. |
| Database / Auth | Supabase | |
| Queue | Managed Redis (Upstash, Redis Cloud, ElastiCache) | Use `rediss://` in production. |
| Storage | Cloudflare R2 or S3 | Private bucket + CORS (above). |

Production checklist:
- `APP_ENV=production`, `AUTH_MODE=supabase`, a strong `API_SECRET_KEY` (the app refuses to start otherwise)
- `CORS_ORIGINS` / `FRONTEND_URL` set to the real frontend origin; HTTPS everywhere
- `SENTRY_DSN` for API and worker; `METRICS_TOKEN` if you scrape `/metrics`
- Run uvicorn behind a trusted proxy with `--proxy-headers` so per-IP rate limits see real client IPs

### Backups and restore
- **Database:** enable Supabase point-in-time recovery, or run scheduled `pg_dump -Fc "$DATABASE_URL" > virello.dump`;
  restore with `pg_restore --clean --no-owner -d "$DATABASE_URL" virello.dump`, then `alembic upgrade head`.
- **Media:** turn on bucket versioning or replicate to a second bucket. Database rows reference storage keys, so restore
  both to the same point in time.

### Logging and monitoring
API and worker write one JSON object per line to stdout with `correlation_id`, `job_id`, `path`, `status` and
`duration_ms` where relevant. Bearer tokens, signed-URL signatures and API keys are redacted. Every error response
includes `error.code`, a safe `error.message` and `error.correlation_id`, and the same ID is in the
`X-Correlation-ID` header, so a user-reported ID maps to the logs. Alert on `/ready` failing and on
`virello_jobs{status="failed"}` growth.

---

## Security notes
- Ownership is enforced on every resource lookup; inaccessible resources return 404 to prevent enumeration.
- RLS is enabled on all tables (defense in depth for any direct PostgREST access).
- Uploads: extension allow-list, declared-size enforcement, magic-byte sniffing, FFprobe validation, plan limits.
- Signed URLs expire (default 15 min); local-storage tokens are HMAC-signed and bound to an operation, key, size and
  content type.
- Rate limits on auth, project creation, upload initiation, renders and retries (Redis-backed).
- Security headers and CSP on the web app; `nosniff`, `X-Frame-Options`, `Referrer-Policy` (and HSTS in production)
  on the API.
- URL import is deliberately unsupported. It needs SSRF-hardened fetching and per-platform authorization, so the UI
  explains this and recommends direct upload.

## Known limitations
- **Codec support in the editor preview:** the editor plays the source in the browser. Codecs a browser can't decode
  (for example HEVC in some browsers) show an explanatory message, and times can still be entered manually. A
  server-generated H.264 preview proxy would remove this limitation.
- Uploads use a single presigned PUT (S3 caps a single PUT at 5 GB). Multipart/resumable uploads are a follow-up.
- Rendering never upscales: a 720p landscape source becomes a 404×720 vertical clip.
- Docker images were written but not built in the development sandbox, because its network blocks Docker Hub and Debian
  package mirrors. CI or any normal machine can build them.
