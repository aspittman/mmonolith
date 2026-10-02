# Product research services

`scholarship_research` and `investor_research` are top-level MMonolith workloads.
They research globally. Geography is a matching criterion, not a Utah restriction.
The customer-facing applications remain separate repositories and runtimes.

## Ownership and current state

| Component | Owns | Current implementation |
| --- | --- | --- |
| MMonolith | Discovery, issuer verification, sourced facts, criteria, duplicate/conflict detection, deadlines and report publication | Both research packages, direct Supabase transport, bounded discovery and verified-source imports |
| CRM/Supabase | Organization-scoped intelligence and engine configuration | Additive migration 024; existing `intelligence_reports`/`organization_services` |
| Decision Engine | Student/company criteria checks and explainable rankings | `product_matching.py` and service-specific matching policies; assessment stored in decision-run summaries |
| dsorchestrator | Research → matching workflow routing | Two-stage declarations; automatic scheduling disabled, production adapters not activated |
| DevSpace One | User-approved applications/checklists/reminders or investor contact | Not configured; no submissions or outreach |
| dsmonitor | Observe only actual participating engines and persistence receipts | MMonolith, Decision Engine and CRM; optional execution/coordinator remain NOT_CONFIGURED |
| Schopath / investor app | Authentication, profile/request UX and displaying results | Schopath exists separately; investor app and product-to-engine bridge are not implemented here |

These engine packages are not scholarship/investor applications. They contain no
client login, no user-facing UI, and no automatic investment or application action.
Missing live source access or profiles remains unconfigured/unknown.

## Research

```bash
.venv/bin/python -m services.scholarship_research \
  --organization ORG_UUID --run-key global-scholarships-unique \
  --discover --publish
.venv/bin/python -m services.investor_research \
  --organization ORG_UUID --run-key verified-investors-unique \
  --source-export /path/real-investors.json --issuer-domains official-issuer.example \
  --publish
```

Discovery uses the configured SerpAPI credential. Its results are unverified leads,
not verified awards or investment mandates. Authorized source exports contain:

```json
{
  "organization_id": "ORG_UUID",
  "service_id": "scholarship_research",
  "is_test": false,
  "opportunities": [{
    "program_id": "stable-program-and-cycle-id",
    "name": "Real issuer's program name",
    "url": "https://official-issuer.example/program",
    "is_test": false,
    "normalization_reviewed": false,
    "facts": {},
    "criteria": []
  }]
}
```

For verified imports each fact is `{value, quote, source_url}`. Criteria additionally
specify `field` and `operator` (`in`, `eq`, `gte`, `lte`). Every quotation must occur
on the freshly fetched, explicitly configured issuer page. Redirects, private
addresses and oversized/non-text responses are rejected. The engine verifies the
quotation; a trusted research reviewer must review its normalized interpretation
before setting `normalization_reviewed: true`. An unrelated quotation does not
establish the meaning of a normalized value. No AI-invented fact becomes evidence.

Scholarship facts: deadline (timezone-aware ISO timestamp), fixed/rolling deadline
type, award minimum/maximum, currency, application URL, confirmed requirements
completeness, accepting applications. Investor facts: check minimum/maximum,
currency, investment mandate completeness, accepting applications, last investment
date, portfolio companies, recent investments, current activity and application URL.
Missing amounts, criteria, deadlines and activity are absent rather than invented.
Amount bands are source currency values, never implicitly converted or interpreted
as total funding-round limits. Source authority depends on the configured issuer
allowlist; this is not automatic authority scoring of search results.

Reports use `SCHOLARSHIP_RESEARCH` or `INVESTOR_RESEARCH`, canonical `service_id`,
`research_contract: product-research-v1`, and `coverage: global`. Opportunity IDs
are deterministic issuer/program keys. Duplicate conflicts require re-research;
expired records remain explainable. Research never evaluates a person's eligibility.
Batch confidence is the fraction of records with issuer verification and reviewed
normalization; it is not outcome probability. Each run is a batch snapshot. Historical
reports remain in Supabase; the matcher uses the latest fresh snapshot for a service.

Publication uses the existing direct Supabase `loop_publish` contract. Organization
service enablement is mandatory. Durable retries are service/org/run-key scoped;
changed export content or source configuration needs a new run key. No live research
uses demo fixtures. No weekly schedule is installed for these new services yet.

## Profiles and matching

For engine-side integration, each enabled organization's existing service row can
hold `config_json.matching_profiles`:

```json
{"matching_profiles":[{"id":"PROFILE_UUID","attributes":{"gpa":3.4,"residence_country":"US","residence_region":"UT","study_level":"Undergraduate","field_of_study":"Computer Science"}}]}
```

This is an initial backend configuration contract, not a student account/profile
API. Do not put student names, contact details or other private account information
in organization service settings. A product bridge must enforce individual account
ownership and consent before sending the necessary eligibility attributes to the
engine. No profiles are fabricated or automatically copied from another product.

Investor attributes include industry, stage, country, region, business model,
funding amount/currency and annual revenue. Investor profile IDs are likewise UUIDs.
Scholarship attributes include country/region of residence, citizenship, study
level/field, GPA, age and financial need. Unsupported fields remain unknown.
Country/region codes and stage/degree vocabularies must agree with the source's
normalized criteria; matching does not guess equivalences or convert GPA scales.

Decision Engine checks each profile independently against each linked candidate.
Fresh issuer evidence (30 days), reviewed normalization, complete requirements,
current availability and known mandatory profile attributes are necessary for a
positive criteria assessment. Failing explicit criteria produces INELIGIBLE or
INCOMPATIBLE. Missing information produces RESEARCH_FURTHER. Expired opportunities
are ranked last. The score measures extracted criteria coverage, not likelihood of
an award or investment. Every check retains its reason and issuer quotation.
No match authorizes submission, purchase, outreach or an application acceptance.

## Existing Schopath application

`/home/aaron/MyBotz/schopath` is a Flutter app with existing student onboarding,
`profiles`, `scholarships`, `scholarship_requirements`, verification records and
Dart matching. Its README calls for a separate Supabase project. Its database has
not been merged into CRM and its production catalog has not been connected here.
Decision Engine accepts Schopath's `country`, `state`, `major` and `education_level`
as aliases for residence country/region, study field and study level. This does not
connect data transport or replace its existing matcher. A future backend bridge
should project verified catalog records and account-owned requests/results using
Schopath's actual schema; service-role credentials must remain server-side.

## Rollout on 2026-10-02

Migration 024 is deployed to the CRM Supabase project. Both research services are
enabled for DevSpace’s internal organization (`2ee8ba95-35f4-4af9-b746-12071ed8815a`).
Initial live discovery reports were published without demo data. They are discovery
leads with zero issuer-verified records, not an app-ready verified catalog. There are
no saved student/company matching profiles. The CRM monitoring route changes are
local code and still need the normal GitHub/Vercel deployment. No product application,
investor outreach adapter, live product bridge or periodic schedule was activated.
