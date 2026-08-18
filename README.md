# Demand Seeker

Demand Seeker is a standalone Python bot that measures the business problems customers are trying to pay to solve. It keeps collection and raw history outside DevSpace CRM, builds local aggregates, and can send only those aggregates to the CRM. Independent, opt-in intelligence modules live under `services/` and do not alter the original demand pipeline.

## File structure

```text
demand_seeker/
├── main.py
├── config.py
├── requirements.txt
├── .env.example
├── collectors/
│   ├── base.py
│   ├── upwork.py
│   ├── reddit.py
│   └── google_trends.py
├── analysis/
│   ├── classifier.py
│   ├── technology_extractor.py
│   ├── pain_point_extractor.py
│   ├── demand_analyzer.py
│   ├── trend_analyzer.py
│   ├── scorer.py
│   └── reporting.py
├── crm/client.py
├── storage/database.py
├── data/
│   ├── raw/upwork.example.csv
│   └── processed/
├── logs/
└── tests/
```

## Data flow

1. Each enabled collector returns the same `Observation` shape. Upwork reads a user-provided CSV, Reddit reads public search RSS, and Google Trends optionally supplies relative search-interest signals.
2. Title and description are jointly classified into a business-service taxonomy. Technologies and pain points are extracted into separate fields; React, Stripe, and similar names never become services by themselves.
3. Normalized observations are deduplicated by `(source, source_id)` and retained in local SQLite. A failed collector is logged and does not stop the others.
4. Analysis compares the last 7/previous 7 and last 30/previous 30 days. Request volume, share, budgets, source diversity, growth, demand, opportunity, and confidence are calculated. Missing budgets remain `null`. Google Trends signals are not counted as paid requests.
5. JSON and CSV reports are written under `data/processed`, a readable summary is printed, and report history is saved locally.
6. If explicitly enabled, the CRM client sends only aggregate services and technologies to DevSpace CRM. Raw titles, descriptions, URLs, and observations stay local.

## Install

```bash
cd /home/aaron/MyBotz/demand_seeker
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

## Environment

The collector switches and scoring weights are documented in `.env.example`. Important values are:

- `COLLECT_UPWORK`, `COLLECT_REDDIT`, `COLLECT_GOOGLE_TRENDS`
- `UPWORK_CSV_PATH`
- `REDDIT_QUERIES`, `REDDIT_LIMIT_PER_QUERY`, `REDDIT_USER_AGENT`
- `GOOGLE_TRENDS_KEYWORDS`, `GOOGLE_TRENDS_GEO`
- `DAYS_SHORT`, `DAYS_LONG`, confidence threshold, and demand weights
- `CRM_SYNC_ENABLED`, `CRM_BASE_URL`, `BOT_API_SECRET`

No secret is hardcoded. With `CRM_SYNC_ENABLED=false`, all commands remain local and make no CRM request.

## Run

```bash
python3 main.py                 # collect, analyze, write/print report, sync only if enabled
python3 main.py --collect       # collect into SQLite only
python3 main.py --analyze       # analyze SQLite and write reports
python3 main.py --report        # print latest report, generating one if absent
python3 main.py --sync-crm      # sync latest report only when CRM_SYNC_ENABLED=true
python3 main.py --google-play   # run the independent Google Play niche service
python3 main.py --trends       # run watch + discovery attention intelligence
python3 main.py --trends --trends-cadence daily  # daily/weekly/monthly policy
```

Flags may be combined, for example `python3 main.py --collect --analyze --report`.

## Collector readiness

- **Upwork CSV:** functional immediately after copying an authorized export to `data/raw/upwork.csv`. Column aliases are supported; use `data/raw/upwork.example.csv` as the canonical format. It intentionally does not scrape Upwork or bypass access controls.
- **Reddit RSS:** functional immediately with network access. It uses public RSS, a descriptive user agent, low configurable limits, and no authentication bypass. RSS availability and Reddit rate limits still apply.
- **Google Trends:** optional and disabled by default. It uses the unofficial `pytrends` client, requires network access, and may be throttled or break when Google changes behavior. Its values are relative search interest—not customer request counts.

## CRM work still required

The inspected DevSpace CRM uses `Authorization: Bearer ${BOT_API_SECRET}` for bot routes, but it does not currently expose the market-demand endpoint. Add:

```text
POST /api/bot/market-demand
Authorization: Bearer <BOT_API_SECRET>
Content-Type: application/json
```

The request body has `generated_at`, `periods`, aggregate `services`, and aggregate `technologies`. Each service includes its category, period counts, demand share, weekly/monthly growth, average/median budget and sample size, demand/opportunity/confidence scores, top technologies, top pain points, and represented source names. The exact payload is produced by `CRMClient.build_payload()`.

Recommended CRM storage is one report/import record plus child service and technology snapshot rows keyed by `generated_at` and period. Preserve nullable growth and budget fields. Do not add a raw-observation table to the CRM for this bot. Competition should remain nullable/unknown.

## Example terminal output

```text
MARKET DEMAND REPORT

1. Payment Integration
   Demand: 82.4/100
   Trend: +25.0%
   Median Budget: $600
   Confidence: 71.0/100

FASTEST GROWING TECHNOLOGIES
1. Stripe (+20.0%, 18 mentions)
2. OpenAI (+12.5%, 9 mentions)
```

## Example report excerpt

```json
{
  "generated_at": "2026-08-07T12:00:00+00:00",
  "periods": {"short_days": 7, "long_days": 30},
  "services": [
    {
      "category": "API_INTEGRATION",
      "requests_7d": 143,
      "requests_previous_7d": 112,
      "weekly_growth_pct": 27.7,
      "median_budget": 600.0,
      "demand_score": 88.0,
      "opportunity_score": 82.0,
      "confidence": 91.0
    }
  ],
  "technologies": [
    {"technology": "Stripe", "mentions_7d": 54, "weekly_growth_pct": 18.2}
  ]
}
```

The real report contains additional fields described above. Scores are comparative decision aids, not fabricated market facts; inspect sample sizes and confidence alongside every score.

## Google Play market intelligence service

`services/google_play` ranks focused app niches using demand, dissatisfaction, competition quality, monetization evidence, market and maintenance gaps, vertical specificity, build complexity, and evidence confidence. It detects `PROVEN_BUT_HATED`, `PROVEN_BUT_ABANDONED`, `SEARCH_DEMAND_WEAK_RESULTS`, and `OVERSIZED_SOFTWARE` patterns. Review analysis extracts recurring complaint themes and their frequency among sampled negative reviews instead of producing only a sentiment score.

```text
provider -> provider-neutral models -> review/scoring analysis -> quality gates
         -> JSON report + SQLite historical snapshots
```

The original collectors, reports, and CRM payload remain unchanged. Google Play reuses the configured SQLite file and output directory but owns tables prefixed with `google_play_`. Snapshots append rather than overwrite.

### Run and configuration

The bundled fixture/import provider supports a credential-free sample run:

```bash
python3 main.py --google-play
python3 -m unittest discover -s tests -v
```

Output is saved at `data/processed/google_play/latest_google_play_report.json`. JSON is used because nested evidence and complaint clusters do not map cleanly to CSV; the existing service's CSV reporting was not duplicated.

Tune the service with the `GOOGLE_PLAY_*` settings documented in `.env.example`: countries, score/confidence gates, evidence thresholds, competition and build-complexity ceilings, maximum results, review sample size, paths, and historical tracking. `GOOGLE_PLAY_ENABLED` is reserved for a future scheduler. The explicit flag runs the service, while ordinary bot runs do not.

### Providers, provenance, and future Play Console data

`GooglePlayProvider` is the adapter contract. `JSONFixtureProvider` reads authorized exports, manual research, or permitted third-party API transformations and needs no key. `PlayConsoleProvider` is the boundary for future first-party installs, conversion, search terms, retention, ratings, country, and revenue data; it intentionally remains unimplemented until an authorized feed is supplied.

To add AppBrain or another provider, subclass `GooglePlayProvider`, return `NicheResearch` records, and inject it into `GooglePlayService(provider=...)`. Network adapters should implement source-specific rate limiting, bounded retries, caching, and timeouts. This project does not evade anti-bot protections.

Competitor evidence is labeled `measured`, `estimated`, or `inferred`. Missing installs, pricing, update dates, and monetization fields remain null. The bundled JSON is illustrative test data, not live market research.

`google_play_score` measures opportunity quality; `confidence_score` measures evidence depth. Demand gates the opportunity calculation, preventing an empty market from ranking well merely because it has no competition. Recommendations also account for confidence, competition, and feasibility rather than one cutoff.

Future Play Console search terms can be normalized into the same provider-neutral records. Terms with unusually strong conversion can create new research seeds—such as a standalone paint estimator—without changing analysis, storage, or reporting.

## Trends: attention velocity and commercial discovery

`services/trends` is MMonolith's broad attention sensor. It does not replace the original demand pipeline or `google_play`. It asks what people are beginning to care about, measures how that attention changes, filters for durable commercial behavior, and persists qualified route jobs for specialist services.

```text
TrendProvider(s) -> provider-neutral histories / related queries / geography
                 -> conservative trend families
                 -> short + medium + long horizon analytics
                 -> attention signal + commercial signal + confidence
                 -> append-only snapshots / transitions / route queue
                 -> google_play, service_intelligence, domain_intelligence
```

The trading-inspired model is:

```text
attention -> history -> velocity -> acceleration -> persistence
          -> lifecycle stage -> commercial trend signal
```

Provider indexes are normalized with symmetric percentage changes before comparison. In particular, a Google Trends value is relative interest within the requested query/time/geography—not absolute searches. Evidence remains labeled `measured`, `normalized`, `estimated`, or `inferred` in provider records and snapshots.

### Scores and lifecycle

These three scores deliberately answer different questions:

- `attention_score`: momentum of the attention phenomenon. It combines level, normalized velocity, acceleration, persistence, geographic breadth, and volatility. Commercial fit has no material role.
- `commercial_trend_score`: usefulness to MMonolith. It rewards velocity, acceleration, persistence, commercial/vertical search behavior, geography, and broad market relevance while penalizing volatility, competition, and likely event spikes.
- `trend_confidence_score`: strength of evidence, not attractiveness. It uses history length, provider count, data completeness, time-horizon/provider agreement, sample size, persistence, and noise. A high commercial score with low confidence remains a watch/investigation signal.

Every signal retains independent `short`, `medium`, and `long` metrics. Defaults are 30, 180, and 1,825 days. The lifecycle classifier emits `DISCOVERY`, `EMERGING`, `ACCELERATING`, `BREAKOUT`, `MAINSTREAM`, `SATURATED`, `DECLINING`, `EVENT_SPIKE`, or `INSUFFICIENT_DATA`. Append-only snapshots make transitions such as `EMERGING → ACCELERATING` first-class report records.

### Watch, discovery, families, and second-order searches

`WATCH_MODE` fetches configured topics and answers what changed in known markets. `DISCOVERY_MODE` accepts provider-supplied trending/rising evidence and answers what MMonolith did not know to watch. Expansion is not a keyword permutation generator: only provider-confirmed rising related queries above `TRENDS_MIN_CHILD_SIGNAL` become children, bounded by depth, children-per-topic, and total discovery limits.

Similar roots and intent branches are grouped into families, so `AI receptionist`, `AI receptionist pricing`, and `AI receptionist for plumbers` can be evaluated together. Related queries are classified as `INFORMATIONAL`, `PROBLEM_AWARE`, `SOLUTION_AWARE`, `COMMERCIAL`, `TRANSACTIONAL`, or `VERTICAL_SPECIFIC`. A rising shift from broad queries toward vertical and transactional terms raises commercial intent.

### Providers and resilience

`TrendProvider` defines `fetch_trending`, `fetch_history`, `fetch_related_queries`, `fetch_geo_interest`, and `normalize`. Included adapters are:

- `ManualJSONProvider`: working credential-free import and deterministic sample provider.
- `ManualCSVProvider`: explicit future import boundary.
- `GoogleTrendsProvider`: optional conservative `pytrends` implementation for watched history, related queries, and regional interest.

The default sample run uses JSON and makes no network request. Google does not offer a generally available official Google Trends API for this use here; the community `pytrends` adapter is unofficial, may be throttled, and is intentionally not enabled by default. Inject it with `TrendsService(providers=[GoogleTrendsProvider(...)])` when that tradeoff is acceptable. A production provider should use an authorized API/export and keep provider-specific rate limits, bounded retry/backoff, timeouts, and caching. Provider failures are recorded and isolated so another source can complete the run. Cached provider payloads avoid unnecessary repeated fetches.

The model supports multi-source evidence now: sources and source snapshots are stored separately and signals are labeled `SINGLE_SOURCE_SIGNAL`, `GOOGLE_ONLY_SIGNAL`, or `MULTI_SOURCE_SIGNAL`. Future Reddit, YouTube, GitHub, jobs, marketplace, domain, funding, and first-party adapters can return the same records without changing scoring or storage.

### Historical storage and routing

The service owns append-only tables prefixed with `trend_`: runs, topics, families/members, snapshots, source snapshots, related queries, geography, signals, routes, failures, and provider cache. It reuses the configured SQLite database but does not alter existing tables. Snapshot JSON includes all headline metrics, horizon metrics, evidence provenance, stage, recommendation, and destinations.

Only signals passing the route score and confidence gates create `pending` route records. Event/noise filters and `IGNORE` signals never route. A route payload is structured for downstream consumption:

```json
{
  "source_service": "trends",
  "topic": "AI receptionist for contractors",
  "stage": "EMERGING",
  "attention_score": 75.0,
  "commercial_trend_score": 80.5,
  "confidence": 70.7
}
```

Use `TrendsStorage.pending_routes("google_play")` from a scheduler/dispatcher to claim candidates for deeper analysis. Routes are persisted as intents; the trends run does not automatically spend external API quota or execute another service. This keeps cross-service handoff meaningful, auditable, and idempotent per signal/destination.

### Configuration, scheduling, and outputs

All strategy and fetch settings use the `TRENDS_*` variables in `.env.example`: modes; countries/regions/categories; watched topics; three windows; attention/commercial/confidence/spike gates; discovery and expansion bounds; routing gates; history/cache controls; provider timeout/retries; and fixture/output paths. Thresholds are not scattered through pipeline code.

Run locally with:

```bash
python3 main.py --trends --trends-cadence daily
python3 main.py --trends --trends-cadence weekly
python3 main.py --trends --trends-cadence monthly
python3 -m unittest discover -s tests -v
```

Daily runs are intended for discovery and short spikes; weekly runs refresh velocity, acceleration, intent shifts, and expansion; monthly runs provide transition/structural review. An external cron, systemd timer, or MMonolith scheduler should invoke those commands. The service itself avoids introducing a resident scheduler. Cache TTL prevents every cadence from refetching unchanged provider data.

Human-readable output is printed and JSON is written to `data/processed/trends/latest_trends_report.json`. `data/raw/trends.example.json` is illustrative normalized data—not live research—and produces an example route to `google_play`. Geographic breadth is computed from provider regions; new-location adoption can be added by providers as repeated geographic snapshots accumulate. Competition level and optional `competition_velocity` are stored independently, including an `attention velocity - competition velocity` evidence gap.
