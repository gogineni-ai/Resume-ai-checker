# Public career-page collection

The `career_html` collector discovers same-site job links from configured public career pages, reads embedded JobPosting JSON-LD, and stores postings and immutable evidence snapshots using the existing database pipeline. No API key or login is used.

Set `CAREER_HTML_SOURCES` on the backend to a JSON list of company sources. For example (replace the example URL with a real career site):

```json
[{"company":"Example Company","urls":["https://example.com/careers"],"max_pages":30}]
```

Company must match the structured hiringOrganization name; unrelated companies are excluded. Sources refresh daily while the Render service is awake and retry after an hour if a run fails. This is bounded discovery from explicit career sites, not a search-engine-wide or all-platform scraper. The existing Greenhouse and Lever feeds continue independently.

The collector checks robots.txt, waits between requests, limits each run to 100 pages per source and the configured registry to 500 sources, processing the 20 oldest-due sources per hourly batch, and rejects non-public HTTPS destinations. Redirects, authentication challenges, rate limits, and JavaScript-only pages are not bypassed. A source without any matching structured postings is recorded as failed, not as a successful empty import. Collection permission and source terms must be reviewed when configuring a site.

Only source-provided datePosted values become historical posting dates. A current advertisement does not prove that the employer used a skill in an earlier year or that a candidate worked there. Duplicate identifiers use the existing snapshot update path.

Standalone collection also accepts sources with `"source":"career_html"` in the normal `collect_jobs.py --config` input.
