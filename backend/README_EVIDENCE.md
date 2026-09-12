# Greenhouse and Lever evidence feeds

The collector uses the public Greenhouse Job Board API and Lever postings feed. It stores each posting in `job_postings` and an immutable content snapshot in `posting_snapshots`. A later change to the same posting creates a new snapshot instead of overwriting the earlier evidence.

1. Copy `sources.example.json` to a private `sources.json`.
2. Set a company name and its public Greenhouse board token or Lever site name. Keep each source disabled until it has been checked.
3. Run from the backend directory:

```text
python collect_jobs.py --config sources.json
```

For a periodic run, use an hourly-or-longer interval:

```text
python collect_jobs.py --config sources.json --interval 86400
```

Greenhouse's public feed includes current job content but does not promise the original posting date, so those records are stored with `posted_at = null` and `date_basis = unknown`. Lever's `createdAt` is stored as a source creation date and labeled `lever_createdAt`; it should not be described as the company's first use of a technology.

The evidence endpoint returns the earliest dated posting and source snippets. A dated posting supports “the company advertised Python in that posting,” not “the company first used Python in that year.”

## Built-in starter boards
Set EVIDENCE_COLLECTION_ENABLED=true to collect Highstreet (Lever highstreetit) and Sphere IT Consultants DWC LLC (Greenhouse sphereit). The single-process web service checks hourly and refreshes successful sources after 24 hours. Failed runs retry after one hour. Free-service sleep pauses collection; due runs resume on startup. This is not a guaranteed wall-clock scheduler. Keep one web worker/instance; use a dedicated scheduler with distributed locking before scaling. Collection dates are not posting dates. Existing analyses are snapshots and require a new scan to use updated evidence.
