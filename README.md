# Resume Verifier AI

A GitHub-ready full-stack application that analyzes a resume against a target job description **and** an archive of company job postings.

## What it does

- Upload PDF, DOCX, or TXT resumes.
- Extract technical skills/tools from the resume.
- Store job descriptions from manual imports and public ATS feeds.
- Compare a resume with a selected target job for ATS-style fit.
- Show matched and missing technologies.
- Cross-check each detected technology against archived job descriptions.
- Flag impossible/likely timeline conflicts when a resume appears to claim a technology before its public availability.
- Keep evidence examples (company, job title, posting year, source URL) for auditability.
- Avoid declaring a person dishonest: output is `supported`, `plausible`, `weak evidence`, or `timeline conflict`.
- Optionally enrich each analysis with an LLM review grounded in retrieved job-posting context.

## Architecture

```text
Browser / Next.js
      |
      v
FastAPI REST API
  |       |         |
Resume   Analyzer   Job ingestion
parser   engine     Greenhouse / Lever / CSV
  \        |        /
        PostgreSQL

    ```

    Optional AI enrichment:

    ```text
    Resume + target job
      |
      v
    LangGraph workflow: retrieve -> analyze -> validate
      |                  |
      v                  v
    Chroma vector DB       OpenAI-compatible LLM
      |
      v
    Retrieved job context + structured recommendations
```

### Stack

- Frontend: Next.js + React + TypeScript
- Backend: FastAPI + Python
- Database: PostgreSQL (SQLite fallback for local backend-only testing)
- NLP: rule-based technology taxonomy + TF-IDF semantic similarity
- AI/ML: optional OpenAI-compatible LLM analysis, LangGraph agent workflow, Chroma vector database RAG
- Ingestion: Greenhouse Job Board API, Lever Postings API, manual/CSV imports
- Deployment: Docker Compose
- CI: GitHub Actions

## Why historical data needs an archive

Current ATS job-board APIs are useful for collecting live published postings but should not be treated as universal multi-year history. For older evidence, ingest licensed historical datasets, company exports, or job descriptions you are legally allowed to store. Save the original source URL and posting date so every finding can be audited.

## Quick start

```bash
git clone <your-repo-url>
cd resume-verifier-ai
docker compose up --build
```

Open `http://localhost:3000`. API docs are at `http://localhost:8000/docs`.

## Import jobs

### Greenhouse

```bash
curl -X POST http://localhost:8000/api/jobs/import/greenhouse/BOARD_TOKEN
```

### Lever

```bash
curl -X POST http://localhost:8000/api/jobs/import/lever/SITE
```

### Manual posting

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H 'content-type: application/json' \
  -d '{"company":"Acme","title":"Data Scientist","description":"Python SQL AWS machine learning"}'
```

### CSV archive

Use `sample_data/jobs.csv` as a template. The included importer posts rows through the API.

```bash
pip install requests
python scripts/import_csv.py sample_data/jobs.csv
```

## Main API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/resumes` | Upload and parse a resume |
| POST | `/api/jobs` | Add a job description |
| GET | `/api/jobs` | List archived jobs |
| POST | `/api/jobs/import/greenhouse/{board_token}` | Import current Greenhouse postings |
| POST | `/api/jobs/import/lever/{site}` | Import current Lever postings |
| POST | `/api/analyze/{resume_id}?target_job_id=1` | Run match + evidence analysis |

## Scoring model (MVP)

`overall = 55% target-job ATS + 30% evidence coverage + 15% timeline consistency`

The ATS score combines explicit technology overlap with TF-IDF semantic similarity. This is intentionally transparent. For production, replace/augment it with embeddings and calibrated models, but keep the deterministic evidence fields visible.

## Optional LLM and RAG analysis

The core analyzer is always available offline. AI enrichment is disabled unless explicitly enabled, and failures in the optional pipeline do not fail a resume analysis. When enabled, the service uses LangGraph to coordinate three steps:

1. Retrieve semantically similar archived job postings from Chroma.
2. Ask an OpenAI-compatible model for a grounded review using only the resume, target job, and retrieved context.
3. Validate the response into structured `summary`, `strengths`, `gaps`, `recommendations`, and `confidence` fields.

Install the backend dependencies, then configure the service with environment variables:

```bash
AI_ENABLED=true
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4o-mini
VECTOR_DB_PATH=./.chroma
AI_TOP_K=4
```

The result from `POST /api/analyze/{resume_id}` includes an `ai_insights` object with `status`, retrieved job references, and model recommendations. Chroma stores embeddings locally at `VECTOR_DB_PATH`; use a managed vector database or a PostgreSQL/pgvector deployment for production scale. Do not send resumes or job data to an external model without the required user consent, retention controls, and provider agreement.

## Production roadmap

1. Parse experience into employer/project/date blocks instead of analyzing the resume only as one document.
2. Associate each claimed skill with the specific job where it is claimed.
3. Add technology release/version knowledge with citations and version dates.
4. Replace local Chroma with managed pgvector embeddings for semantic search over millions of job postings.
5. Add OpenSearch/Elasticsearch for keyword + metadata filtering.
6. Add background workers (Celery/RQ/Kafka) for ingestion.
7. Add object storage (S3/GCS) and virus scanning for uploads.
8. Add authentication, tenant isolation, RBAC, audit logs, rate limiting, encryption, retention/deletion controls.
9. Add connectors for licensed historical-job datasets instead of scraping sites that prohibit it.
10. Add evaluation datasets, prompt/version tracking, and human review for LLM summaries.

## Important interpretation rule

A historical job description can show that a technology was used or requested by an employer at a point in time. It **cannot prove** that a particular candidate personally used that technology. The application therefore reports evidence strength and conflicts, not accusations of falsification.

## License

MIT for the sample application. Verify the license/terms of every external job-data source you connect.

## Product UI and authentication

The frontend now includes a full SaaS-style experience inspired by the approved mockup:

- Email/password login page
- Create-account page with full name, email, phone number and password
- Signed access-token authentication
- PBKDF2-SHA256 password hashing (passwords are never stored in plaintext)
- Per-user resume uploads and analysis history
- Responsive authenticated app shell with branded header and sidebar
- Resume upload and archived-job selector
- Pasted job-description analysis
- Match/result dashboard with ATS, evidence, timeline and semantic metrics
- Skill verification/timeline page
- Analysis history page
- Account settings page

### Authentication routes

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

Set a long random `AUTH_SECRET` outside local development. The demo token implementation is signed with HMAC and expires after seven days. For an internet-facing production deployment, use HTTPS, secure HttpOnly cookies or an external identity provider, email/phone verification, rate limiting, password-reset flows, and database migrations.
