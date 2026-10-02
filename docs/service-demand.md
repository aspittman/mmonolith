# DevSpace service demand

The current question is **what technical services show evidence of demand?**
Pricing, rates and capacity do not block this research. Testing a service, approving
an offering and sending outreach are later decisions.

The implementation is in `services/devspace_services`. Google Play now lives in
`services/devspace_services/google_play`; all entry points import this canonical package. Google Play's existing product/app
rankings remain separate from the new `SERVICE` hypotheses. Negative app reviews
can also become attributed pain evidence for integration or reporting services.

## Evidence

The live starter scan uses Remotive's public software-development job feed and up
to eight SerpAPI queries. Remotive is attributed and each job retains its source
link. Hiring is a demand proxy, not an outsourced project request. Job dates have
day precision. Public search results retain query and retrieval time; publication
date, whether a request is still active and purchase intent remain unverified.
Successful search queries are cached for 24 hours. Partial provider failures remain
visible in `provider_failures` and `collection_status` rather than discarding
successful sources.

Authoritative marketplace exports, Google Play review exports and live trend
measurements can augment the scan:

```bash
.venv/bin/python -m services.devspace_services --organization ORG_UUID \
  --run-key unique-cycle --jobs --search --publish
.venv/bin/python -m services.devspace_services --organization ORG_UUID \
  --run-key marketplace-cycle --upwork /path/dated-jobs.csv --publish
.venv/bin/python -m services.devspace_services --organization ORG_UUID \
  --run-key review-cycle --google-play /path/live-play-export.json \
  --trends /path/live-trends-report.json --publish
```

An Upwork CSV needs `title`, `description`, `url`, `posted_at` and optionally
`job id`; timestamps must include timezone. Missing dates and links are excluded.
JSON observations use `{ "organization_id": "UUID", "observations": [...] }`.
Each observation needs `source`, `record_id`, public HTTPS `url`, timezone-aware
`observed_at`, `text`, `kind` and explicit `is_test: false`. Kinds are
`buyer_request`, `job_posting`, `review_pain`, `search_interest`,
`competitor_offer`, `technical_pain`, `technology_change`, `web_mention`. Do not label unverified
search snippets as buyer requests.

Google Play imports use the existing `niches`/`apps`/`reviews` schema, with
`demo_data: false`, dated reviews and real Play links. Trend reports retain raw
`source_observations`; normalized search interest never becomes buyer counts.
Existing demo fixtures cannot silently produce live service reports.

Records are deduplicated by source ID and URL, and limited to the last 30 days.
Keyword matching starts with API integration, performance, analytics, website
fixes, SEO, app maintenance, website builds and AI integration. These are search
hypotheses, not an exhaustive market catalog. Missing matching evidence means
unknown demand, not zero demand. Review language needs explicit matching terms;
the initial classifier does not interpret every synonym or negation.

`research_strength_score` ranks evidence for investigation, not sales likelihood
or ROI. Buyer-request counts, hiring observations, app complaints and web mentions
remain separate. Source coverage and low confidence make proxy-only results
explicit. `observed_request_share_percent` refers only to imported requests, with
overlapping categories; it is not market share. Percentage changes require supplied
comparable measurements with equal-duration windows, source dates and units.
A zero baseline yields unknown percentage growth.

## Storage and decisions

Research reads and publishes directly to Supabase through the existing
`loop_publish` RPC. Migration `023_service_demand.sql` persists canonical service
identity without inventing workflow runs or granting execution permissions.
Only DevSpace's own enabled organization service may publish these reports.
Run keys include `devspace_services:` and exact payloads are retained in a durable
organization-scoped outbox. Retrying a saved run does not search or create another
report. Use a new key for new research.

Decision Engine's `strategies/devspace_services/demand.py` reads the latest fresh
`SERVICE_DEMAND` report and records its assessment in
`decision_runs.summary.service_assessments`. It prioritizes explicit requests and
hiring evidence, distinguishes indirect evidence, excludes foreign/test/stale
reports, and never authorizes execution. Existing outreach strategies remain
separate. Reports link historical execution outcomes through recommendation
evidence and request IDs; drafts, replies and null revenue do not establish sales.

The runner `scripts/run_service_demand.py` chains research and the existing CRM
decision endpoint. Stable ISO-week keys prevent repeated research in one week.
The installed schedule runs Tuesday at 07:30 host time and preserves existing jobs.
It does not approve recommendations, publish an offering or send email.

Dsmonitor verifies MMonolith's actual direct connection with bounded
tenant/service-scoped reads under DevSpace's own organization. CRM and decision
endpoint checks remain separate. Real publication receipts carry report IDs;
successful reads alone never claim writes or completed handoffs.

Once demand is supported, the next phase is an explicitly approved service test:
choose the offer and buyer segment, define outreach and a success measurement,
then record replies, meetings, purchases and invoices. `TEST_SERVICE`,
`OFFER_SERVICE`, `CONTINUE_SERVICE` and `RETIRE_SERVICE` are not enabled by this
demand-only rollout.

Source documentation: https://github.com/remotive-io/remote-jobs-api

## Full source set and independent confirmation

All eight requested categories are supported:

| Source | Collection | Meaning |
| --- | --- | --- |
| Upwork | Dated authorized CSV (`--upwork`) | Explicit outsourced buyer requests |
| Reddit | Public RSS (`--reddit`) or authorized JSON (`--reddit-export`) | Technical/business pain; exports can contain explicit requests |
| Google Trends | Live measured report (`--trends`) | Search interest and comparable changes, not purchases |
| Google Play | Live review export (`--google-play`), existing authorized provider | App pain; product rankings remain separate |
| Fiverr | Authorized listing JSON (`--fiverr-export`) | Competitor supply, not proof of buying demand |
| GitHub Issues | Public API (`--github-issues`) or authorized JSON | Technical pain, excluding pull requests |
| Stack Overflow | Public API (`--stack-overflow`) or authorized JSON | Technical pain, respecting provider backoff |
| Other boards | Remotive (`--jobs`) or authorized JSON (`--job-boards-export`) | Hiring proxy or explicitly identified freelance requests |

JSON source exports require `organization_id`, `demo_data: false`, and
`observations` using the dated schema above. Source-specific imports enforce
platform URLs and allowed evidence kinds. Fiverr exports cannot label listings
as buyer requests. API queries are bounded and currently start with API integrations
and website performance; use `--technical-max-queries 8` for broader manual research.
`DEVSPACE_GITHUB_TOKEN` optionally supplies GitHub API access. Reddit access may
be rejected; rejection remains a failed source rather than being bypassed.

`source_connectors` lists every category as UNCONFIGURED, COLLECTED, PARTIAL or
FAILED, with collected counts. COLLECTED can mean zero returned records and does
not establish zero market demand. The weekly runner now attempts Reddit, GitHub
and Stack Overflow alongside jobs and public search. Exports must be selected
explicitly for manual runs; no demonstration fixtures feed the schedule.

Each service has `corroboration`: independent platform count, platform names,
source/kind matrix, buyer-source count, and declining-interest evidence IDs.
Platform aliases count once. Long identical syndicated text counts once across
platforms. Search snippets and competitor supply never count as demand
confirmation; declining search interest is not positive confirmation.
Cross-source pain/hiring/interest without buyer requests remains corroborated
proxies. A heuristic research score favors multiple independent sources over
large volumes from one source. It estimates research priority, not purchases.
Decision Engine reconstructs confirmation from linked observations rather than
trusting the publisher's source count or score. Its assessments remain advisory.

Public API references:
[GitHub issues](https://docs.github.com/en/rest/issues/issues),
[GitHub search](https://docs.github.com/en/rest/search/search), and
[Stack Exchange advanced search](https://api.stackexchange.com/docs/advanced-search).
