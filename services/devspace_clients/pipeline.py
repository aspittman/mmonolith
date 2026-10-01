"""Client research reports preserve evidence and observed outcomes without forecasts."""
from dataclasses import replace
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5
from .modules import MODULES
from .profiles import strings


def build_report(profile, provider, config, context, run_key, is_test=False):
    if any(row.get('organization_id') != profile.organization_id for rows in context.values() for row in rows):
        raise ValueError('Cross-organization history rejected')
    tracks = [('customers', profile.queries, profile.target_terms)]
    for objective, key in (('referrals', 'referrals'), ('competitors', 'competition')):
        track = config.get(key, {})
        if track:
            tracks.append((objective, strings(track.get('queries', []), key + '.queries', True),
                strings(track.get('target_terms', []), key + '.target_terms', True)))
    # Each track has its own explicit bounded query allowance. All findings retain their purpose.
    researched = {}
    for objective, queries, terms in tracks:
        scoped = replace(profile, objective=objective, queries=queries, target_terms=terms)
        rows = provider.discover(scoped)
        candidates = MODULES['prospect_discovery'](scoped, rows, provider.name)
        if 'website_audit' in profile.modules:
            MODULES['website_audit'](candidates)
        researched[objective] = candidates
    competition = researched.pop('competitors', [])
    competitors = {c['domain'] for c in competition}
    opportunities = [c for candidates in researched.values() for c in candidates if c['domain'] not in competitors]
    # One business may be both a customer and referral partner; keep distinct objective identities.
    for c in opportunities:
        c['id'] = c['id'] + ':' + c['objective']
        c['competition_context'] = {'researched_competitors': len(competition),
            'limitations': 'Search sample only; market share, pricing and demand remain unknown.'}
    subject = 'client:' + profile.profile_id
    history = [r for r in context.get('intelligence_reports', []) if
        r.get('report_type') == 'CLIENT_RESEARCH' and r.get('subject_key') == subject and r.get('is_test') == is_test]
    previous = max(history, key=lambda r: (r['created_at'], r['id'])) if history else None
    # Outcomes must point to this service's reports through the existing recommendation evidence.
    report_ids = {r['id'] for r in history}
    rec_ids = {e['recommendation_id'] for e in context.get('recommendation_evidence', []) if e.get('intelligence_report_id') in report_ids}
    requests = {q['id']: q for q in context.get('execution_requests', []) if q['recommendation_id'] in rec_ids}
    outcomes = [r for r in context.get('execution_results', []) if r['execution_request_id'] in requests and
        r.get('status') == 'COMPLETED' and r.get('results', {}).get('is_test', False) == is_test]
    metadata = {'service_id': 'devspace_clients', 'research_contract': 'client-research-v1',
        'profile_id': profile.profile_id, 'profile_config': config, 'business_type': profile.business_type, 'offer': profile.offer,
        'opportunities': opportunities, 'competitors': competition,
        'outcome_history': [{'execution_result_id': r['id'], 'metrics': r.get('metrics', {})} for r in outcomes],
        'limitations': ['Fit scores are keyword/location heuristics, not conversion forecasts.',
            'Search-query geography does not verify prospect location.', 'No email is sent by research.'],
        'counts': {k: len(v) for k, v in researched.items()}}
    return {'report': {'run_key': run_key, 'subject_key': subject, 'subject_type': 'client_market',
        'report_type': 'CLIENT_RESEARCH', 'summary': f'{profile.business_type}: {len(opportunities)} customer/referral findings and {len(competition)} competitor findings for review.',
        'overall_score': None, 'confidence_score': max((c['fit_confidence'] for c in opportunities), default=0),
        'previous_report_id': previous['id'] if previous else None,
        'correlation_id': str(uuid5(NAMESPACE_URL, profile.organization_id + ':devspace_clients:' + run_key)),
        'is_test': is_test, 'metadata': metadata}, 'signals': [], 'predictions': [], 'feedback_ids': []}


def run_profile(profile, provider, config, client, outbox, run_key, *, publish=False, is_test=False):
    if not run_key or len(run_key) > 182:
        raise ValueError('run_key must have 1–182 characters')
    # CRM's immutable publication key is organization-scoped across all services.
    run_key = 'devspace_clients:' + run_key
    saved = outbox.get('devspace_clients', profile.organization_id, run_key)
    if saved:
        bundle, record_id = saved
        if bundle['report']['is_test'] != is_test or bundle['report']['metadata']['profile_id'] != profile.profile_id:
            raise ValueError('Run key scope/mode mismatch')
    else:
        context = client.context(profile.organization_id) if client else {}
        bundle = build_report(profile, provider, config, context, run_key, is_test)
        bundle = outbox.save('devspace_clients', profile.organization_id, run_key, bundle)
        record_id = None
    if publish and record_id is None:
        if client is None:
            raise ValueError('CRM transport required for publication')
        record_id = client.publish(profile.organization_id, bundle)
        outbox.acknowledge('devspace_clients', profile.organization_id, run_key, record_id)
    return {'organization_id': profile.organization_id, 'run_key': run_key,
        'intelligence_report_id': record_id, 'report': bundle['report']}
