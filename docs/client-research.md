# DevSpace client growth

`devspace_clients` is independent of `domain_merchant`. Each service has its own
folder, organization settings, reports, outbox and monitoring identity. MMonolith's
service folders are listed in `services/catalog.json`; the other engines list
their folders in `SERVICE_FOLDERS.json`. Legacy domain and strategy imports remain
compatible. Common HTTP transport, monitoring receipts and publication retries
live under `services/shared`.

## Client onboarding

The authenticated CRM portal now directs clients without a completed profile to
`/portal/business-profile`. There is no public self-signup endpoint in the existing
CRM: this covers the first login after the existing account creation/invitation
process, and lets existing clients update their profile through the sidebar.

The form captures business type, offering, customer description and search terms,
referral partners, competitor context, service areas and excluded websites. It
saves to `organization_services.config_json.client_research` with service key
`devspace_clients` and niche `client-growth`. The save RPC derives organization
ownership from the authenticated profile. It cannot enable email, approve an
execution request, edit another organization, or modify unrelated service config.

Utah is the initial area. Six starter profiles were prepared from the
existing inventory and the supplied business descriptions in
`data/devspace_clients/initial_profiles.json` and registered in Supabase, with
`needs_client_confirmation=true`; their target categories are initial hypotheses.
Synapse needs a business description. Domain Merchant, Apollo Outreach and the
internal DevSpace organization are excluded from this initial client list.

## Research modules and tracks

`services/devspace_clients/modules.py` contains the research module registry.
The first module discovers prospects and applies an explicit keyword/location
fit heuristic. An optional website module observes HTTP availability. Add specialized
business logic as another module rather than forking the scheduler or CRM client.

Customer, referral and competition tracks have separate search terms and queries.
Businesses found in the competition track are excluded from outreach opportunities.
One organization can have multiple service profiles; the profile ID is part of
its subject and run identity. Search results are deduplicated by website per track.

The SerpAPI connector uses `SERPAPI_API_KEY` or `SERP_API_KEY` from the environment.
Each track has an explicit query limit (the form sets three); a three-track client
uses at most nine search calls. Failed provider requests fail that client's run,
and other clients continue. Raw transport exceptions are suppressed because query
URLs contain credentials. Authorized JSON exports can run entirely offline.

Every opportunity retains its sources, query, research purpose, fit rationale,
confidence and missing information. Query geography is not verified location.
Fit is not a buying-intent, market-share or conversion forecast. Competitor samples
do not establish market saturation. Reports therefore have a null overall market
score and no invented predictions or normalized market signals.

## Run

Install the repository requirements and provide `CRM_BASE_URL`, `BOT_API_SECRET`
and a search key for connected runs. The client research module is invoked explicitly;
the existing demand/trends/Domain Merchant scheduling is preserved.

```bash
python3 -m services.devspace_clients --provider serpapi --run-key weekly-2026-40 --publish
python3 -m services.devspace_clients --organization ORG_UUID --provider serpapi --run-key manual-001 --publish
```

Only enabled `devspace_clients` service profiles are fetched. Missing required
business information fails that client, rather than inventing an offering.
The CLI emits one status per client and exits nonzero for an empty roster or any
failed client. Publication payloads are saved before HTTP submission. Reusing a
run key retries the exact saved payload without repeating research; a new cycle
requires a new run key. Run keys are prefixed with the service identity in the CRM.

For offline runs, `--profiles` is a JSON array of service rows, and `--export`
contains `{ "organization_id": "UUID", "prospects": [...] }`. Each prospect has
`company_name`, `website`, `description`, optional `contact`, `location`,
`location_evidence` (`source` only for verified source geography), and `objective`
(`customers`, `referrals`, or `competitors`; omitted defaults to customers).

```bash
python3 -m services.devspace_clients --profiles /path/profiles.json --organization ORG_UUID --export /path/prospects.json --run-key export-001
```

Local reports are under `data/devspace_clients/reports/ORG_UUID/`. The outbox is
`data/devspace_clients/publications.sqlite3`. Use `DEVSPACE_ENV=test` with `--test`
for explicitly synthetic inputs. Test reports do not produce live brief requests.

## Decision and execution

The decision engine's separate `strategies/devspace_clients/brief.py` selects a
fresh client report and recommends `CLIENT_OUTREACH_BRIEF` for its reviewable
opportunities. This means existing evidence can be prepared for review; its
confidence of 1 is explicitly about draftability, not sales or prospect quality.
Organization enablement, client policy, adapter readiness and active requests
still apply. A completed brief for the exact report is not recommended again.

The existing admin recommendation screen approves the zero-spend request. The
CRM's separate `loop_claim_client_brief` checks its service, action, constraints,
readiness and explicit draft-only flags. DevSpace One prepares bounded briefs:

```bash
python3 -m services.devspace_clients.worker --organization ORG_UUID
```

Results contain customer/referral purpose, offer, evidence, missing information
and recipient/message review requirements. No email is sent by this adapter.
Each result is locally saved before CRM submission and replayed idempotently.
Future sending must connect these approved/reviewed briefs to the delivery
pipeline; this rollout does not represent draft counts as delivered outreach.
The next research report incorporates attributable execution metrics from prior
client reports without changing market confidence or creating sales forecasts.

## Deployment readiness

Live migrations 019–022 have been applied. Six client profiles are registered,
and the initial cycle published through the Supabase `loop_publish` contract.
The scheduled runner uses `ClientResearchSupabase` for profile reads, context,
and publication through the existing `loop_publish` RPC. Research does not depend
on Vercel availability. Decision and draft preparation retain their CRM endpoints.
Dsmonitor checks the research service with bounded, tenant/service-scoped direct
Supabase reads using the same backend credential. Client monitoring has its own
six-business scope in `dsmonitor/scripts/client_monitoring_scope.json`; other
service scopes remain independent. Successful reads never manufacture write
verification: actual publication receipts retain their record IDs.
The tested CRM release is commit
`4b93063` in `/tmp/devspace-crm-client-deploy`; its onboarding endpoint must return
200 before the form and draft worker are considered live.
Migration 022 adds onboarding, the separate recommendation type and draft claim,
and leaves the adapter disabled. After deploying the verified DevSpace One worker,
register `execution_capabilities.devspace_clients.adapter_ready=true` to allow
approved draft requests to queue. This does not authorize email delivery.

Use the business form or explicitly register reviewed starter profiles, then
schedule research weekly using a stable cycle key. Run the decision engine with
`NEW_INTELLIGENCE_REPORT` after publication, and poll the client brief worker for
approved requests. Deployment and runtime activation are separate from code tests.

The host runner uses the local virtual environment and reads existing backend
credentials without exposing them:

```bash
.venv/bin/python scripts/run_client_cycle.py --research
```

The first cycle successfully published reports for all six registered clients.
Weekly research is installed for Monday at 06:30 host time, preserving the
existing cron jobs. The default cycle key is the UTC ISO week, so repeat runs reuse completed payloads.
Use `--decide` and `--prepare` only after the CRM release is deployed. The runner
does not approve recommendations or send email.
