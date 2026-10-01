# Domain research from observed evidence

## Ownership

MMonolith now owns domain candidate research. The original pure Domain Merchant
research modules live in `devspace_domain_research`, including the old scorer,
valuation, sales importers and grammar analysis. They were preserved, not deleted.
`transfer_manifest.json` records their original source hashes. DevSpace One retains
compatibility import paths and its service registry, portfolio and outreach code.
Its Domain Merchant runner consumes MMonolith findings instead of generating or
scoring its own candidates.

The new `domain-evidence-v1` report contains individual reported comparable sales,
keyword measurements, potential-buyer observations and dated registrar quotes.
Unknown evidence stays unknown. Candidate generation uses observed sales patterns
or explicitly supplied research seeds; generated names are hypotheses. The optional
`--legacy-comparison` field is labeled heuristic and does not select candidates.
No resale probability or expected profit is invented from reported sale prices.

Decision Engine applies configurable evidence requirements and existing business
constraints. Its score is policy-check coverage, not a valuation. CRM retains
versioned reports and projects candidates into the existing Domain Portfolio UI.
DevSpace One's safe worker consumes only the approved report's selected candidates.
The prediction/result feedback cycle remains described in
[the architecture](closed-loop-intelligence.md).

**Remaining boundary:** existing CRM SMTP sending functionality remains unchanged.
This transfer does not make DevSpace One the sole sender in every legacy workflow.
Production execution through the new feedback worker is intentionally disabled;
only approved test investigations are supported there.

## Installation

Install MMonolith's shared research package in each Python environment used by
DevSpace One. Use a normal wheel installation, not an editable installation: the
repositories have different top-level `services` packages.

```bash
cd /path/to/mmonolith
python3 -m pip install .
cd ../devspace-one
python3 -m pip install ../mmonolith
python3 -m pip install -r requirements.txt
```

For separate deployments, build a wheel with `python3 -m pip wheel --no-deps .`
and distribute/install that wheel before DevSpace One's requirements. The package
is local; version 0.2 is not published to a public package registry.

Apply CRM migrations in their existing order, including
`016_feedback_loop.sql` and **`017_domain_research_projection.sql`**. The latter
adds same-organization report lineage to leads and an atomic, idempotent
`loop_publish_research` RPC. No deployed migrations were applied by this work.
Existing bearer authentication, approval routes and RLS remain authoritative.
The intelligence POST endpoint selects this RPC for `domain-evidence-v1` reports.
The existing `domain_merchant` service/source key is retained for compatibility;
`research_owner=mmonolith` identifies the actual producer.

## Collect facts locally

A free keyword-aggregate lookup, with no CRM writes:

```bash
cd /path/to/mmonolith
python3 -m services.domain_intelligence.discover \
  --organization 11111111-1111-4111-8111-111111111111 \
  --run-key hvac-research-001 --niche hvac --keyword hvac \
  --location nevada --namebio-live
```

NameBio aggregates alone do not satisfy the Decision Engine's individual comparable
sales, buyer, demand and quote requirements. Reports show these missing inputs.
Use a new run key for a new collection; replaying the same organization/run key
reuses the saved publication bundle, even if command options have changed.

Add authorized evidence as available:

- `--namebio-file FILE`, `--dnjournal-file FILE`, `--sales-file FILE`: reuse the
  transferred importers and existing sales formats. Existing files in DevSpace One
  remain where they were; pass their paths. Asking prices, invalid/nonfinite prices,
  future sales and ineligible transactions are excluded.
- `--with-keywords`: explicitly enables the existing **billed** DataForSEO API.
  Set `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`, optionally
  `DATAFORSEO_LOCATION_CODE` (default 2840) and `DATAFORSEO_LANGUAGE_CODE` (default en).
  Raw search volume/CPC are retained; they are not domain resale demand.
- `--demand-file FILE`, `--retail-file FILE`: reuse previously collected provider
  envelopes without a network call.
- `--registrar-check`: read-only Namecheap `domains.check` and `users.getPricing`.
  Set `NAMECHEAP_API_USER`, `NAMECHEAP_API_KEY`, `NAMECHEAP_USERNAME`,
  `NAMECHEAP_CLIENT_IP`; API access and an allowlisted IP are required. Records
  include acquisition and renewal prices, currency, timestamp and separate fees.
  No registration command exists in this adapter. Quotes must be rechecked before
  any real purchase. `--availability-file FILE` supports existing static imports.
- `--buyers-file FILE`: an authorized, tenant-specific buyer evidence envelope.
  No additional live Apollo connector was introduced. Existing Apollo integration
  stays in DevSpace One. Example shape (replace with observed facts):

```json
{
  "organization_id": "YOUR_ORGANIZATION_UUID",
  "subject_key": "hvac|nevada",
  "source_url": "https://your-authorized-source.example/record",
  "retrieved_at": "2026-09-15T12:00:00+00:00",
  "companies": [
    {"domain": "observed-business.example", "fit_reason": "Observed HVAC business in Nevada"}
  ]
}
```

Buyer samples are deduplicated observed businesses, not total market size. Do not
use the illustrative entry above as evidence. Subject keys are niche, optionally
`|` plus sorted comma-separated locations.

## Publish, recommend and evaluate

Set MMonolith `CRM_BASE_URL` and `BOT_API_SECRET`; append `--sync-crm` to discovery.
Set `DEVSPACE_ENV=test` for test records in all Python components. Local collection
without `--sync-crm` does not require CRM credentials.

```bash
# Decision Engine: existing CRM_API_URL and CRM_API_SECRET
cd /path/to/decision_engine
DEVSPACE_ENV=test python3 main.py --organization "$ORG" --trigger NEW_INTELLIGENCE_REPORT

# Review and approve the resulting recommendation in CRM.
# DevSpace One: existing CRM_BASE_URL and CRM_BOT_API_SECRET
cd /path/to/devspace-one
DEVSPACE_ENV=test python3 -m core.feedback_worker --organization "$ORG" --fixture /path/to/test-execution.json

# MMonolith: evaluate attributable results, then publish a new version
cd /path/to/mmonolith
DEVSPACE_ENV=test python3 -m services.domain_intelligence --organization "$ORG" --learn
```

Run discovery again with a **new run key** and `--sync-crm` to include stored
outcomes/evaluations and link the predecessor. Run Decision Engine again to consume
that new version. The older `python3 -m services.domain_intelligence --evidence ...`
interface remains available for normalized reports; use `discover` for raw domain
facts. Discovery does not automatically invent numerical predictions when evidence
cannot justify one. The safe fixture explicitly supplies a synthetic prediction.

Confidence is an evidence-sufficiency indicator: individual sales `n/(n+3)` times
coverage across sales, demand, buyers and availability. Feedback adjustments are
bounded to 0.05 before sample-size weighting, deduplicated per result, and averaged.
It is not a probability of sale. External facts and internal execution results
remain separate. Policy thresholds are in Decision Engine `config/scoring.json`.

## Provider requirements and limitations

- [NameBio API](https://api.namebio.com/docs/): free retail keyword aggregates,
  with NameBio attribution retained in CRM. Cached 24 hours; local calls separated
  by at least 16 seconds. A real free `hvac` lookup was verified. Aggregates lack
  individual sale dates, a TLD filter and an unsold inventory denominator.
  Individual transaction access/imports still require appropriate access/licensing.
- [DataForSEO search-volume API](https://docs.dataforseo.com/v3/keywords_data/google_ads/search_volume/live/):
  paid credentials required; reuses MMonolith's transport, caches 30 days.
  No paid request was made during validation.
- [Namecheap availability](https://www.namecheap.com/support/api/methods/domains/check/)
  and [pricing](https://www.namecheap.com/support/api/methods/users/get-pricing/):
  credentials/IP authorization required. Quotes cache 15 minutes, standard pricing
  24 hours. Parser and read-only command tests passed; live credentials not tested.
- DNJournal and individual NameBio sales use authorized files; no scraper added.
- Automated buyer collection, sell-through estimates from unsold inventory,
  production worker execution and sole-sender consolidation remain future work.

Provider failures are recorded as missing evidence, not substituted with scores.
Caches never store API credentials. Research bundles may contain private buyer
facts; protect local output/cache paths using the same organization access rules
as other research artifacts.

## Safe verification

See [the validation record](closed-loop-validation.md) for the actual trace.
The disposable test starts PostgreSQL, PostgREST and CRM locally, exercises the
real Domain Portfolio and approval UI, and uses synthetic evidence/outcomes.

```bash
cd /path/to/mmonolith
/tmp/de-crm-venv/bin/python scripts/smoke_domain_loop.py \
  --engine-root ../decision_engine --postgrest /tmp/de-postgrest/postgrest
```

The workspace test dependencies are already installed. Portable setup is in the
architecture guide; also install this repository's research package into that test
interpreter. No purchase or outreach is performed. The JSON trace includes report,
recommendation, request, result, evaluation, updated report and next recommendation
IDs. Logs include correlation/organization IDs; no secrets should be logged.
