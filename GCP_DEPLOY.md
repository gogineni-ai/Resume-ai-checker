# Deploy Resume Verifier AI to Google Cloud (Cloud Run + Cloud SQL)

Recommended route: **Cloud Run for both services + Cloud SQL for Postgres**.
This keeps the app stateless (Cloud Run) and the data durable (Cloud SQL).
Do NOT rely on the local SQLite fallback or the local `./.chroma` folder on
Cloud Run: the filesystem is ephemeral and a new instance loses it.

## What was changed for Google Cloud in this copy

- `backend/Dockerfile`: now listens on `$PORT` (Cloud Run sets this, usually
  8080) instead of hard-coded 8000.
- `frontend/Dockerfile`: now listens on `$PORT` instead of hard-coded 3000,
  and uses `npm ci` for a reproducible build.
- `backend/app/config.py`: added the two settings `email_service.py`
  already uses — `resend_api_key` and `otp_from_email`. Without them,
  registering a user crashed with an AttributeError instead of failing
  gracefully when email is not configured.
- `backend/app/main.py`: added `POST /api/analyses/{analysis_id}/interview-prep`
  — a deterministic interview-prep agent that needs no LLM key. It turns
  missing skills into gap questions and matched skills into depth questions.
- Added `.dockerignore` files so local build artefacts are not shipped.

## Existing agents (already in the repo, no change needed)

- LangGraph agent in `backend/app/services/ai_pipeline.py`:
  retrieve (Chroma) -> analyze (OpenAI-compatible LLM) -> validate.
  Only runs when `AI_ENABLED=true` and `OPENAI_API_KEY` is set. Core
  analysis still works with it off.
- Resume coach: `POST /api/coach/chat` (LLM when configured, fallback text
  otherwise).
- Analysis chat / rewrite: `POST /api/analyses/{id}/chat` and `/rewrite`
  (rule-based, grounded in the stored analysis).

## Suggested agents to add next (not yet implemented)

1. Job-ingestion agent: watch Greenhouse/Lever sources, dedupe, and post
   new jobs on a schedule (Cloud Scheduler -> backend `/api/jobs/refresh`
   or a Cloud Run Job). Keep the existing evidence rules: a posting proves
   advertised demand, never a candidate's personal use.
2. Evidence agent: for a company + skill, return the dated sightings with
   source URLs, and flag timeline conflicts. Most of this already exists
   in `GET /api/evidence`; it mainly needs a UI page.
3. Outreach / follow-up agent: only after email is configured — draft
   follow-ups from an analysis, never send without user approval.

## Before you run the deploy script

You need, and this environment does not currently have:

1. A Google Cloud account with billing enabled.
2. A GCP project ID (e.g. `resume-ai-checker-prod`).
3. The `gcloud` CLI, authenticated (`gcloud auth login` and
   `gcloud config set project <PROJECT_ID>`).
4. A region, e.g. `us-central1` (pick the one closest to your users).
5. Secrets, created in Secret Manager (never committed):
   - `AUTH_SECRET`: a long random string. The default in code
     (`change-this-secret-in-production`) must never be used live,
     or anyone could forge login tokens.
   - `DB_PASSWORD`: the Cloud SQL user password.
   - Optional: `RESEND_API_KEY` + `OTP_FROM_EMAIL` — required in practice,
     because uploads and analysis are gated on email verification.
     Without working email, a new user can register but cannot upload
     a resume until they verify.
   - Optional: `OPENAI_API_KEY` + `AI_ENABLED=true` for the LLM agents.

## Deploy (from this repo root)

```bash
export PROJECT_ID=phonic-oxide-508515-k1
export REGION=us-central1
bash deploy-gcp.sh
```

What the script does, in order:

1. Enables `run.googleapis.com`, `sqladmin.googleapis.com`,
   `secretmanager.googleapis.com`, `artifactregistry.googleapis.com`.
2. Creates an Artifact Registry repo and builds + pushes the backend
   and frontend images.
3. Creates a Cloud SQL Postgres 16 instance (`db-g1-small` to start),
   a database `resume_verifier`, and a user `resume`.
4. Deploys the backend to Cloud Run with `--add-cloudsql-instances`,
   passing `DATABASE_URL` using the Cloud SQL Unix socket, plus
   `AUTH_SECRET` from Secret Manager.
5. Deploys the frontend to Cloud Run, building it with
   `NEXT_PUBLIC_API_URL` set to the live backend URL. This matters:
   that variable is baked in at build time, so the frontend must be
   built *after* the backend URL is known.
6. Prints both service URLs. Test with:
   - Backend: `<BACKEND_URL>/health` should return `{"ok": true}`
   - Frontend: open `<FRONTEND_URL>`, register, verify email, upload
     a resume.

## Costs to expect (rough, check current GCP pricing)

- Cloud Run: pay-per-use; near zero at idle with `min-instances=0`.
- Cloud SQL `db-g1-small`: this is the main fixed cost, roughly
  tens of dollars per month, even at idle. If you want the cheapest
  possible running demo, a single Compute Engine VM running the
  existing `docker-compose.yml` is cheaper, but you then own OS
  patching, backups, and uptime yourself.

## Things to fix before real users, not just a demo

- Restrict CORS to your frontend URL only (currently set from
  `CORS_ORIGINS`, so set it to exactly the frontend URL).
- Put the frontend behind HTTPS only (Cloud Run gives this by default)
  and set `FRONTEND_URL` / OAuth redirect URIs to the live URLs.
- Turn off public sign-up or add rate limiting if you do not want
  open registration.
- Back up Cloud SQL and set a retention policy for uploaded resumes.
