# Solstice Check-in Kiosk Service

An event check-in kiosk backend for Solstice Events Co.'s multi-day tech conference. Staff scan an attendee's QR code to trigger a badge print; the service guarantees each attendee is checked in — and printed — exactly once.

## Background & Pivot

The original design called the venue's badge-printer vendor **synchronously**: the app sent a print request, blocked until the vendor's REST API returned a success response, and only then displayed "Checked In."

The vendor deprecated that synchronous API with no extension. This service was rebuilt around an **asynchronous model**:

1. On scan, the app atomically claims the attendee (preventing any duplicate claim) and publishes a print job to the vendor's message queue.
2. The UI shows a `PENDING` state immediately — not "Checked In."
3. The vendor calls back a webhook endpoint on this service once the print job actually completes.
4. Only on a successful webhook callback does the attendee's state flip to `CHECKED_IN`.

Duplicate-scan protection holds under this model even when webhook confirmations arrive **out of order** or are retried/duplicated by the vendor.

## Architecture

```
Staff scans QR
      │
      ▼
POST /checkin/{attendee_id}
      │
      ├─ Atomic claim (Redis SET NX) — fails safely if already claimed
      │
      ▼
Publish print job (job_id, attendee_id, callback_url) → Vendor's queue
      │
      ▼
Return { status: "PENDING" } to the kiosk UI
      │
      ⋮  (some time later, possibly out of order)
      ▼
Vendor → POST /webhooks/print-status  { attendee_id, job_id, success }
      │
      ├─ Ignore if job_id doesn't match the currently pending job
      ├─ Ignore if attendee is no longer PENDING (already resolved)
      │
      ▼
Update state → CHECKED_IN (or FAILED)
```

State is stored in **Redis**, keyed by `attendee_id`, and includes a unique `job_id` per print attempt. This is what makes the two safety guarantees possible:

- **No double print:** a second scan of an already-claimed attendee can never win the atomic claim, so it can never trigger a second print job.
- **No double-apply of a webhook:** a callback is only applied if its `job_id` matches the attendee's currently pending job **and** the attendee is still `PENDING` — so retried, late, or out-of-order callbacks are safely ignored instead of corrupting state.

## Tech Stack

- **FastAPI** — async web framework
- **PostgreSQL** (via `asyncpg` + SQLAlchemy) — durable attendee records
- **Redis** (Render "Key Value") — atomic state claims and print-job tracking
- **httpx** — async HTTP client for publishing to the vendor's queue
- **pytest / pytest-asyncio** — test suite

## Project Structure

```
app/
├── main.py                  # FastAPI app entrypoint
├── config.py                # Settings (env-var driven)
├── database.py               # SQLAlchemy/Postgres setup
├── redis_client.py          # Redis connection + atomic state helpers
├── schemas.py                # Pydantic request/response models
├── models.py                 # DB models
├── api/routes/
│   ├── checkin.py            # POST /checkin/{attendee_id}
│   ├── webhook.py            # POST /webhooks/print-status
│   └── admin.py               # Admin/inspection endpoints
└── services/
    ├── checkin_service.py     # Check-in / duplicate-claim logic
    ├── queue_service.py       # Publishes print jobs to the vendor's queue
    ├── webhook_service.py      # Resolves incoming webhook callbacks
    └── notification_service.py

core/
├── exceptions.py
└── logging.py

tests/
├── test_checkin.py
├── test_webhook.py
├── test_concurrency.py
└── test_acceptance.py
```

## Environment Variables

Set these on your hosting platform (not in a `.env` file — this app reads from the real environment, and platforms like Render inject config this way):

| Variable | Example | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/dbname` | Must use the `+asyncpg` driver prefix |
| `REDIS_URL` | `redis://red-xxxxxxxxxxxxx:6379` | Render's "Key Value" internal URL |
| `REDIS_LOCK_TTL` | `30` | Seconds before an unresolved claim expires |
| `REDIS_STATE_TTL` | `600` | Seconds before resolved state expires |

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run (hardcode a port locally — $PORT is a hosting-platform variable, not local)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000/docs` for interactive API docs, and `http://localhost:8000/health` for a health check.

## Deploying (Render)

1. Connect this repo as a **Web Service** on Render.
2. **Start Command:**
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
3. Create a **PostgreSQL** database and a **Key Value** (Redis) instance on Render, in the same region as the web service.
4. Set `DATABASE_URL` and `REDIS_URL` under the web service's **Environment** tab, using the *Internal* connection URLs from each resource (remember to change the Postgres prefix to `postgresql+asyncpg://`).
5. Push to `main` — Render auto-deploys on every push.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/checkin/{attendee_id}` | Scan handler — claims the attendee and publishes a print job. Returns `PENDING` or the existing state if already claimed. |
| `POST` | `/webhooks/print-status` | Vendor callback — resolves a print job by `job_id`. Idempotent; safe against retries and out-of-order delivery. |
| `GET` | `/status/{attendee_id}` | Current check-in state: `NOT_CHECKED_IN`, `PENDING`, `CHECKED_IN`, or `FAILED`. |
| `GET` | `/health` | Service + dependency health check. |
| `GET` | `/docs` | Interactive Swagger UI. |

## Testing

```bash
pytest
```

Test coverage includes:
- A full happy-path check-in (scan → pending → webhook confirms → checked-in)
- Duplicate scan of an already-checked-in attendee (must not publish a second print job)
- Out-of-order webhook delivery (a stale or duplicate callback must not overwrite a resolved state)
- Unknown or already-resolved job callbacks (must be ignored gracefully, not error)

## Known Limitations / Next Steps

- The kiosk UI should poll `/status/{attendee_id}` (or use SSE/WebSocket) while an attendee is `PENDING`, since results are no longer synchronous.
- Free-tier Render Postgres/Redis instances expire after a set period — upgrade before relying on this for a live event.
