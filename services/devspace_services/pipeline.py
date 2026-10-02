"""Produce service hypotheses and preserve attributable commercial outcomes."""
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid5, NAMESPACE_URL
from .catalog import SERVICES
from .evidence import collect
from .corroboration import corroboration, research_score


def build_bundle(org, observations, configuration, history, run_key, *, now=None):
    now=now or datetime.now(timezone.utc)
    evidence=collect(observations,now)
    if any(r.get('organization_id')!=org for rows in history.values() for r in rows):
        raise ValueError('Cross-organization history rejected')
    capabilities=configuration.get('delivery',{})
    direct_count=sum(e['kind']=='buyer_request' for e in evidence)
    opportunities=[]
    for key, service in SERVICES.items():
        linked=[e for e in evidence if key in e['service_ids']]
        if not linked: continue
        requests=[e for e in linked if e['kind']=='buyer_request']
        kinds={e['kind'] for e in linked}; sources={e['source'] for e in linked}
        # A review complaint is not a service purchase. This ranks evidence for investigation.
        strength=research_score(linked)
        delivery=capabilities.get(key,{})
        missing=[] if requests else ['Verified buyer requests; current evidence is indirect']
        blockers=['Testing or outreach requires a separate approved offering and execution plan']
        opportunity={'id':key,'opportunity_type':'SERVICE','name':service['name'],
            'research_strength_score':strength,'score_scope':'Heuristic evidence priority; not expected ROI or probability of sales',
            'evidence_ids':[e['id'] for e in linked], 'explicit_requests':len(requests),
            'observed_request_share_percent':round(len(requests)/direct_count*100,1) if direct_count else None,
            'demand_scope':'Share of imported buyer requests; categories can overlap. Search snippets are unverified leads, not active requests.',
            'job_postings':sum(e['kind']=='job_posting' for e in linked),
            'app_pain_mentions':sum(e['kind']=='review_pain' for e in linked),
            'web_mentions':sum(e['kind']=='web_mention' for e in linked),
            'corroboration':corroboration(linked),'technical_pain_mentions':sum(e['kind']=='technical_pain' for e in linked),
            'source_count':len(sources),'source_kinds':sorted(kinds),'delivery':delivery,
            'competition':{'observed_offers':sum(e['kind']=='competitor_offer' for e in linked),'market_share':None},
            'estimated_price':delivery.get('price'), 'implementation_hours':delivery.get('estimated_hours'),
            'recurring_revenue_potential':delivery.get('recurring_revenue_potential'),
            'recommendation':'RESEARCH_SERVICE',
            'blocking_reasons':blockers, 'missing_information':missing,
            'prospects':[e for e in requests if e.get('buyer')],
            'comparisons':[{'evidence_id':e['id'],**e['comparison']} for e in linked if e.get('comparison')]}
        opportunities.append(opportunity)
    opportunities.sort(key=lambda o:(-o['research_strength_score'],o['id']))
    prior=[r for r in history.get('intelligence_reports',[]) if r.get('report_type')=='SERVICE_DEMAND' and r.get('is_test') is False
        and r.get('metadata',{}).get('service_id')=='devspace_services']
    prior_ids={r['id'] for r in prior}
    recommendations={e['recommendation_id'] for e in history.get('recommendation_evidence',[]) if e.get('intelligence_report_id') in prior_ids}
    requests={r['id'] for r in history.get('execution_requests',[]) if r['recommendation_id'] in recommendations and r.get('execution_service')=='devspace_services'}
    outcomes=[r for r in history.get('execution_results',[]) if r['execution_request_id'] in requests and r.get('status')=='COMPLETED'
        and r.get('results',{}).get('is_test') is False]
    return {'report':{'run_key':'devspace_services:'+run_key,'subject_key':'devspace:service-demand','subject_type':'service_market',
        'report_type':'SERVICE_DEMAND','summary':f'{len(opportunities)} service hypotheses from {len(evidence)} attributed observations; buying outcomes remain separate.',
        'correlation_id':str(uuid5(NAMESPACE_URL,org+':devspace_services:'+run_key)),
        'previous_report_id':max(prior,key=lambda r:(r['created_at'],r['id']))['id'] if prior else None,
        'overall_score':None,'confidence_score':round(min(.85,.15+min(.55,direct_count*.025)+
            (0.15 if len({e['source_family'] for e in evidence if e['kind']=='buyer_request'})>1 else 0)),3) if evidence else 0, 'is_test':False,
        'metadata':{'service_id':'devspace_services','research_contract':'service-demand-v1',
            'configuration':configuration, 'opportunities':opportunities,'evidence':evidence,
            'source_coverage':{'observations':len(evidence),'verified_imported_requests':direct_count,
                'unclassified_observations':sum(not e['service_ids'] for e in evidence),
                'services_without_matching_evidence':[key for key in SERVICES if not any(key in e['service_ids'] for e in evidence)],
                'missing_evidence_is_not_zero_demand':True},
            'outcomes':[{'execution_result_id':r['id'],'metrics':r.get('metrics',{}),'revenue':r.get('revenue'),
                'scope':'Recorded execution outcome; drafts and replies do not establish a purchase'} for r in outcomes],
            'limitations':['Search interest, app complaints and hiring demand are proxies, not paid customer demand.',
                'Unknown feasibility, prices, competition and sales are not fabricated.',
                'App/product opportunities stay in Google Play output and are not ranked as service offerings.']}},
        'signals':[],'predictions':[],'feedback_ids':[]}
