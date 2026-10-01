# Closed-loop validation — 2026-09-15

Validated the current local working trees, preserving existing uncommitted work.

| Check | Result |
| --- | --- |
| MMonolith unittest suite | 42 passed |
| Decision Engine pytest suite, including PostgreSQL | 69 passed |
| DevSpace One unittest suite | 40 passed |
| CRM PostgreSQL migration/approval suite | 8 passed |
| CRM Node API suite | 7 passed |
| CRM lint / typecheck / production build | Passed |
| Four-system safe integration test | Passed |

The integration used real CRM HTTP routes, Domain Portfolio rendering and the
actual recommendation approval form; real strategy/repository/worker code; local
PostgreSQL and PostgREST; and synthetic local authentication. No production Auth
or deployed database was used. MMonolith supplied synthetic raw sales/demand/buyer/
quote evidence. DevSpace One consumed approved candidates without running research.
Delivery/reply/offer measurements were explicitly simulated.

Verified report/prediction immutability, new report lineage, idempotent lead
projection/publication/results, tenant isolation, service credentials unable to
approve, offline-adapter queuing, and a new recommendation using updated evidence.
No domain purchase, production outreach or paid provider call occurred.
Separately, a real free NameBio HVAC aggregate lookup succeeded; live DataForSEO
and Namecheap access remain unverified. No migrations were deployed.

## Trace from disposable local database

```json
{
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "correlation_id": "3e5631dd-e115-5ab4-8881-4f02bb9c1db3",
  "intelligence_report_id": "e16a6461-66f9-4e83-8f63-a37148cb177a",
  "recommendation_id": "c45eb5b7-c2c7-496d-bfd0-a38a63a86e8e",
  "execution_request_id": "beaf14db-c728-4200-af39-36a52f549922",
  "execution_result_id": "0c403d23-2bd0-460f-9b45-248d15a5c6dd",
  "feedback_evaluation_id": "4b72c87e-361b-4acc-af0f-bbe93c992315",
  "updated_intelligence_report_id": "0e47e673-454d-4039-adfe-7c870a39baf4",
  "next_recommendation_id": "09500d84-829a-48a6-bca5-d13a0d5da16f",
  "crm_ui_verified": true,
  "approval_via_crm_form": true,
  "external_actions": 0
}
```

## Reproduce

```bash
cd /path/to/mmonolith
/tmp/de-crm-venv/bin/python scripts/smoke_domain_loop.py --engine-root ../decision_engine --postgrest /tmp/de-postgrest/postgrest
```

See [research setup](domain-research.md) and [architecture](closed-loop-intelligence.md)
for dependencies and configuration. Workspace logs are
`/tmp/domain-transfer/validation-0.log` through `validation-8.log`.
The two additional registrar parser tests were run after the full validation.
The default local Python environment also has the research wheel installed for
DevSpace One compatibility imports. Separate deployment environments need their
own installation.
