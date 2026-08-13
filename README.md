# Demand Seeker

Demand Seeker is a standalone Python bot that measures the business problems customers are trying to pay to solve. It keeps collection and raw history outside DevSpace CRM, builds local aggregates, and can send only those aggregates to the CRM.

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

