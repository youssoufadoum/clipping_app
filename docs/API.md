# Virello Studio API (v1)

Interactive docs run at `/api/docs` (Swagger UI) and `/api/redoc`. The machine-readable spec is served at
`/api/openapi.json`, and a snapshot is committed at [`docs/openapi.json`](./openapi.json). Regenerate it with:

```bash
cd backend && uv run python -m app.cli export-openapi ../docs/openapi.json
```

## Conventions
- Base path `/api/v1`. JSON request and response bodies.
- **Auth:** `Authorization: Bearer <access token>` (a Supabase access token, or a local-dev token when
  `AUTH_MODE=local`). The server derives identity from the verified token only.
- **Errors:** always shaped like
  ```json
  { "error": { "code": "QUOTA_EXCEEDED", "message": "Safe, human-readable text.",
               "correlation_id": "3f2a…", "details": { "retryable": false } } }
  ```
  Common codes: `UNAUTHORIZED`, `TOKEN_EXPIRED`, `NOT_FOUND`, `CONFLICT`, `VALIDATION_FAILED` (with
  `details.fields`), `QUOTA_EXCEEDED`, `FILE_TOO_LARGE`, `UNSUPPORTED_MEDIA`, `UPLOAD_INCOMPLETE`, `RATE_LIMITED`,
  `QUEUE_UNAVAILABLE`, `FEATURE_UNAVAILABLE`, `BILLING_UNAVAILABLE`, `INTERNAL_ERROR`.
- **Pagination:** `?page=1&page_size=20` returns `{ items, total, page, page_size }`.
- Resources you can't access return `404`, never `403`, so IDs can't be enumerated.

## Endpoints

### Health
| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET | `/ready` | DB, queue, storage, ffmpeg checks (`503` if degraded) |
| GET | `/metrics` | Prometheus text; requires `Bearer $METRICS_TOKEN` |

### Auth and account
| Method | Path | Notes |
| --- | --- | --- |
| POST | `/auth/session/verify` | Returns `{ user_id, email, provider }` for the bearer token |
| POST | `/auth/local/register` · `/auth/local/login` | Dev only (`AUTH_MODE=local`); `503 LOCAL_AUTH_DISABLED` otherwise |
| GET / PATCH | `/me` | Profile and onboarding fields |
| DELETE | `/me` | Body `{ "confirm": "DELETE" }`; deletes media, data and the auth user |
| GET | `/system/status` | Public: which features this deployment has configured |

### Projects and uploads
| Method | Path | Notes |
| --- | --- | --- |
| POST | `/projects` | `{ title }` |
| GET | `/projects` | `q`, `status`, `include_archived`, `sort`, pagination |
| GET / PATCH / DELETE | `/projects/{id}` | PATCH `{ title?, archived? }`; DELETE removes all media |
| GET | `/projects/{id}/jobs` | Job history |
| POST | `/projects/{id}/uploads/initiate` | `{ filename, content_type, size_bytes }` → presigned `{ upload_id, method, url, headers }` |
| (client) | `PUT <url>` | Upload the file directly to storage with the returned headers |
| POST | `/projects/{id}/uploads/complete` | `{ upload_id, auto_shorts? }`: verifies the object and queues `inspect_media` (idempotent). With `auto_shorts` `{ target_seconds, count, captions, auto_render }`, AI shorts start automatically after inspection |
| POST | `/projects/{id}/uploads/abort` | Abandon an in-progress upload |
| GET | `/projects/{id}/media` | Assets (source, thumbnails, renders) |
| GET | `/projects/{id}/source-url` | Short-lived URL for previewing the source |
| DELETE | `/media/{id}` | Delete a derived asset (source videos are removed with the project) |

### Processing
| Method | Path | Notes |
| --- | --- | --- |
| GET | `/jobs/{id}` | `status`, `stage`, `progress` (0–1, reported by the worker), `error_code`, `safe_error_message` |
| POST | `/jobs/{id}/cancel` | Queued jobs cancel immediately; running jobs stop at the next check |
| POST | `/jobs/{id}/retry` | Failed or cancelled jobs only; creates a new job |
| POST | `/projects/{id}/jobs` | `{ "job_type": "inspect_media" }` to re-run inspection after a failure |
| POST | `/projects/{id}/analyze` | AI shorts. Body `{ target_seconds: 30\|60, count: 1-5, captions, auto_render, instructions?, language? }`. `503 AI_NOT_CONFIGURED` without `GEMINI_API_KEY`; `402` when AI minutes run out |
| GET / PATCH | `/projects/{id}/transcript` | Read; PATCH `{ segments: [{ index, text }] }` corrects text (timings kept) |

### Clips and exports
| Method | Path | Notes |
| --- | --- | --- |
| GET / POST | `/projects/{id}/clips` | POST `{ title, start_seconds, end_seconds, render_settings? }` |
| GET / PATCH / DELETE | `/clips/{id}` | PATCH any of title, trims, `render_settings` |
| POST | `/clips/{id}/render` (alias `/clips/{id}/exports`) | Quota-checked; returns the render job |
| POST | `/clips/{id}/duplicate` | |
| GET | `/clips/{id}/download?inline=false` | Signed URL to the latest render |
| GET | `/clips/{id}/subtitles?format=srt\|vtt` | Captions for the clip, timed from the clip start |
| POST | `/clips/{id}/captions` | `503 FEATURE_UNAVAILABLE` (captions come from the transcript; set `render_settings.captions`) |
| GET | `/exports` · `/exports/{id}` | Export history · signed download URL |

`render_settings`:
```json
{ "aspect_ratio": "9:16 | 1:1 | 16:9 | original", "fit": "crop | pad",
  "crop_x": 0.5, "crop_y": 0.5, "pad_color": "black | white | 0x111827", "normalize_audio": false,
  "captions": false, "caption_position": "lower | middle" }
```

### Usage and billing
| Method | Path | Notes |
| --- | --- | --- |
| GET | `/usage` | Plan, used/reserved/remaining minutes, policy text |
| GET | `/usage/history` | Ledger entries |
| GET | `/billing/plans` | Public plan limits |
| POST | `/billing/checkout` · `/billing/portal` | `503 BILLING_UNAVAILABLE` until phase 3 |
