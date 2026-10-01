"""Build reviewable sibling-repository changes in /tmp before applying them."""
import hashlib
import json
from pathlib import Path

BASE = Path('/home/aaron/MyBotz')
STAGE = Path('/tmp/client-rollout')
manifest = {}

def modify(repo, path, old, new):
    source = BASE/repo/path
    content = source.read_text()
    if old not in content:
        raise ValueError('Expected source text missing: ' + str(source))
    target = STAGE/repo/path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.replace(old, new, 1))

modify('decision_engine', 'decision_engine/strategies/__init__.py',
    'from .outreach import OutreachStrategy',
    'from .devspace_clients.brief import ClientOutreachBriefStrategy\nfrom .outreach import OutreachStrategy')
path = STAGE/'decision_engine/decision_engine/strategies/__init__.py'
path.write_text(path.read_text().replace('SEOStrategy, DomainResearchReviewStrategy)', 'SEOStrategy, DomainResearchReviewStrategy, ClientOutreachBriefStrategy)'))
modify('decision_engine', 'decision_engine/repositories/crm.py',
    "context.profile['organization_services'] = data['organization_services']",
    "context.profile['organization_services'] = data['organization_services']\n        context.profile['client_execution_results'] = data.get('execution_results', [])")
modify('devspace-crm', 'lib/feedback-loop-api.ts',
    "  } else if(route==='claim-review') {",
    "  } else if(route==='claim-client-brief') {\n   const input=z.object({organization_id:uuid,service:z.literal('devspace_clients')}).strict().parse(body)\n   name='loop_claim_client_brief';args={p_org:input.organization_id}\n  } else if(route==='claim-review') {")
modify('devspace-crm', 'components/layout/sidebar-nav.tsx',
    "  { href: '/portal', label: 'Portal Home' },",
    "  { href: '/portal', label: 'Portal Home' },\n  { href: '/portal/business-profile', label: 'Business Profile' },")
modify('devspace-one', 'core/crm_client.py',
    "context.get('service_id') or 'domain_merchant'",
    "payload.get('results', {}).get('service_id') or context.get('service_id') or 'domain_merchant'")

# Preserve all existing approval/queue behavior; extend only the explicit zero-spend whitelist.
source = (BASE/'devspace-crm/supabase/migrations/021_domain_evidence_review.sql').read_text()
functions = source[source.index('create or replace function public.de_review('):source.index('-- Prediction-free observations')]
old = "r.recommendation_type='MARKET_RESEARCH' and r.execution_service='domain_merchant' and r.metadata->>'action_type'='review_domain_evidence'"
new = "((r.recommendation_type='MARKET_RESEARCH' and r.execution_service='domain_merchant' and r.metadata->>'action_type'='review_domain_evidence') or (r.recommendation_type='CLIENT_OUTREACH_BRIEF' and r.execution_service='devspace_clients' and r.metadata->>'action_type'='prepare_client_outreach' and v_parameters->'draft_only'='true'::jsonb and v_parameters->'send_authorized'='false'::jsonb and v_parameters->'is_test'='false'::jsonb))"
if old not in functions:
    raise ValueError('Approval whitelist has changed')
functions = functions.replace(old, new)
# Domain review's investigation flag is replaced with draft-only for the client exception.
functions = functions.replace("v_parameters->'investigation_only'='true'::jsonb", "(v_parameters->'investigation_only'='true'::jsonb or (r.recommendation_type='CLIENT_OUTREACH_BRIEF' and v_parameters->'draft_only'='true'::jsonb))")
header = '''-- Separate client-growth onboarding and approved zero-spend outreach preparation.
begin;
alter table recommendations drop constraint recommendations_recommendation_type_check;
alter table recommendations add constraint recommendations_recommendation_type_check check
 (recommendation_type in ('OUTREACH','GOOGLE_ADS','META_ADS','SEO','LANDING_PAGE_OPTIMIZATION','WEBSITE_FIX','DOMAIN_ACQUISITION','DOMAIN_OUTREACH','CONTENT','MARKET_RESEARCH','NO_ACTION','CLIENT_OUTREACH_BRIEF'));
insert into execution_capabilities(service_key,status,allowed_actions,adapter_ready)
 values('devspace_clients','AVAILABLE',array['prepare_client_outreach'],false)
 on conflict(service_key) do nothing;
update service_registry set enabled=true,metadata=metadata||'{"category":"client_growth"}'::jsonb where service_id='devspace_clients';
update service_registry set metadata=metadata||'{"category":"domains"}'::jsonb where service_id='domain_merchant';

create function save_client_business_profile(p_config jsonb) returns uuid
language plpgsql security definer set search_path=public,pg_temp as $$
declare org uuid; rid uuid; k text;
begin
 select organization_id into org from profiles where id=auth.uid();
 if org is null then raise exception 'Authenticated business identity required'; end if;
 perform 1 from organizations where id=org for update;
 if jsonb_typeof(p_config) is distinct from 'object' then raise exception 'Business configuration required'; end if;
 foreach k in array array['business_type','offer','ideal_customers','referral_partners','competitors'] loop
  if jsonb_typeof(p_config->k) is distinct from 'string' or length(btrim(p_config->>k))<2 or length(p_config->>k)>2000 then raise exception 'Business description missing'; end if;
 end loop;
 foreach k in array array['locations','target_terms','referral_terms','competitor_terms','queries','modules'] loop
  if jsonb_typeof(p_config->k) is distinct from 'array' then raise exception 'Research targeting required'; end if;
  if jsonb_array_length(p_config->k) not between 1 and 20 or exists(select 1 from jsonb_array_elements(p_config->k) e where jsonb_typeof(e)<>'string' or length(btrim(e#>>'{}'))<2 or length(e#>>'{}')>300) then raise exception 'Invalid research targeting'; end if;
 end loop;
 -- Only business information and bounded research knobs can be changed by customers.
 if (p_config - array['business_type','offer','ideal_customers','target_terms','referral_partners','referral_terms','competitors','competitor_terms','locations','excluded_domains','enabled','objective','modules','queries','referrals','competition','max_prospects','max_queries','min_fit_score'])<>'{}'::jsonb
 or p_config->'enabled' is distinct from 'true'::jsonb or p_config->>'objective' is distinct from 'customers'
 or p_config->'modules' is distinct from '["prospect_discovery"]'::jsonb
 or p_config->'max_prospects' is distinct from '25'::jsonb or p_config->'max_queries' is distinct from '3'::jsonb
 or p_config->'min_fit_score' is distinct from '60'::jsonb then raise exception 'Unsupported profile settings'; end if;
 insert into organization_services(organization_id,service_key,service_name,niche,is_enabled,email_enabled,approval_required,config_json)
 values(org,'devspace_clients','DevSpace Clients','client-growth',true,false,true,jsonb_build_object('client_research',p_config))
 on conflict(organization_id,service_key,niche) do update set
 config_json=organization_services.config_json||jsonb_build_object('client_research',p_config),updated_at=now()
 returning id into rid;
 return rid;
end $$;
revoke all on function save_client_business_profile(jsonb) from public,anon;
grant execute on function save_client_business_profile(jsonb) to authenticated;
'''
claim = '''
create function loop_claim_client_brief(p_org uuid) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare q execution_requests;
begin
 perform 1 from organizations where id=p_org for update;
 perform de_queue_approved(p_org);
 select r.* into q from execution_requests r
 join recommendations rec on rec.id=r.recommendation_id and rec.organization_id=p_org
 join execution_capabilities cap on cap.service_key=r.execution_service
 where r.organization_id=p_org and r.execution_service='devspace_clients' and r.action_type='prepare_client_outreach'
 and r.status='QUEUED' and rec.status='QUEUED' and rec.expires_at>now()
 and cap.adapter_ready and cap.status='AVAILABLE' and r.action_type=any(cap.allowed_actions)
 and r.requested_parameters->'budget_limit'='0'::jsonb
 and r.requested_parameters->'is_test'='false'::jsonb and r.requested_parameters->'draft_only'='true'::jsonb
 and r.requested_parameters->'send_authorized'='false'::jsonb
 and r.requested_parameters->'external_calls_authorized'='false'::jsonb
 and r.requested_parameters->'purchase_authorized'='false'::jsonb
 and r.constraints_snapshot=coalesce((select constraints from decision_constraints where organization_id=p_org),'{}')
 and exists(select 1 from organization_services where organization_id=p_org and service_key='devspace_clients' and is_enabled)
 order by r.created_at,r.id for update of r limit 1;
 if not found then return null; end if;
 update execution_requests set status='RUNNING',updated_at=now() where id=q.id;
 update recommendations set status='EXECUTING',updated_at=now() where id=q.recommendation_id;
 q.status:='RUNNING';return to_jsonb(q);
end $$;
revoke all on function loop_claim_client_brief(uuid) from public,anon,authenticated;
grant execute on function loop_claim_client_brief(uuid) to service_role;
commit;
'''
(STAGE/'devspace-crm/supabase/migrations').mkdir(parents=True, exist_ok=True)
(STAGE/'devspace-crm/supabase/migrations/022_client_growth.sql').write_text(header+functions+claim)

for repo in ('decision_engine', 'devspace-one'):
    p = BASE/repo/'monitoring/profile.json'
    data = json.loads(p.read_text())
    data['services']['devspace_clients'] = {'inputs': ['intelligence_reports', 'execution_results']}
    dest = STAGE/repo/'monitoring/profile.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2)+'\n')
# Group the remaining decision policies by service, retaining public import compatibility.
for source_name, folder, class_name in (('google_ads', 'paid_search', 'GoogleAdsStrategy'),
        ('seo', 'organic_search', 'SEOStrategy'), ('landing_pages', 'landing_page', 'LandingPageStrategy'),
        ('outreach', 'devspace_services', 'OutreachStrategy')):
    content = (BASE/'decision_engine/decision_engine/strategies'/f'{source_name}.py').read_text()
    target = STAGE/'decision_engine/decision_engine/strategies'/folder/'strategy.py'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.replace('from .base import Strategy', 'from ..base import Strategy'))
    package = BASE/'decision_engine/decision_engine/strategies'/folder/'__init__.py'
    if not package.exists():
        (target.parent/'__init__.py').write_text('"""Service-specific decision policies."""\n')
    (STAGE/'decision_engine/decision_engine/strategies'/f'{source_name}.py').write_text(
        f'"""Compatibility import; policy lives in its service folder."""\nfrom .{folder}.strategy import {class_name}\n')

for repo, data in (
    ('decision_engine', {'domain_merchant': 'strategies/domain_merchant', 'devspace_clients': 'strategies/devspace_clients',
        'devspace_services': 'strategies/devspace_services', 'scholarship_research': 'strategies/scholarship_research',
        'investor_research': 'strategies/investor_research', 'google_ads': 'strategies/paid_search',
        'seo': 'strategies/organic_search', 'landing_page': 'strategies/landing_page'}),
    ('devspace-one', {'domain_merchant': 'services/domain_merchant', 'devspace_clients': 'services/devspace_clients',
        'devspace_outreach': 'services/devspace_outreach', 'apollo_outreach': 'services/apollo_outreach',
        'afternic_sync': 'services/afternic_sync'})):
    (STAGE/repo/'SERVICE_FOLDERS.json').write_text(json.dumps(data, indent=2)+'\n')
for file in STAGE.rglob('*'):
    if file.is_file() and file.name != 'manifest.json':
        relative = file.relative_to(STAGE)
        original = BASE/relative
        manifest[str(relative)] = hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None
(STAGE/'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'staged_files': len(manifest), 'root': str(STAGE)}))
