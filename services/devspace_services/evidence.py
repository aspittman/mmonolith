"""Validate attributed demand observations; separate proxies from buying intent."""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import math
import re
from urllib.parse import urlparse
from .catalog import SERVICES
from .corroboration import source_family

KINDS = {'buyer_request', 'job_posting', 'review_pain', 'search_interest', 'competitor_offer', 'technology_change', 'web_mention', 'technical_pain'}


def observed(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None: raise ValueError('Evidence timestamps need a timezone')
    return dt.astimezone(timezone.utc)


def normalize(raw, now, max_age_days=30):
    if raw.get('kind') not in KINDS: raise ValueError('Unknown evidence kind')
    date = observed(raw['observed_at'])
    if not now-timedelta(days=max_age_days) <= date <= now: return None
    url = urlparse(raw['url'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password:
        raise ValueError('Public HTTPS evidence URL required')
    for key in ('source', 'record_id', 'text'):
        if not isinstance(raw.get(key), str) or not raw[key].strip(): raise ValueError('Attributed evidence required')
    if raw.get('is_test') is not False: raise ValueError('Evidence must explicitly declare live or test mode')
    text = raw['text'][:4000]
    service_ids = [key for key, service in SERVICES.items() if any(
        re.search(r'\b'+re.escape(term)+r'\b', text.lower()) for term in service['terms'])]
    identifier = sha256((raw['source']+':'+raw['record_id']).encode()).hexdigest()[:24]
    result = {key: raw[key] for key in ('kind', 'url', 'source', 'record_id', 'observed_at')}
    result['source_family']=source_family(raw)
    result.update(id=identifier, text=text, service_ids=service_ids,
        evidence_scope='Explicit service request' if raw['kind']=='buyer_request' else 'Demand proxy; purchase intent unverified',
        buyer=raw.get('buyer') if isinstance(raw.get('buyer'), dict) else None)
    if raw['kind']=='web_mention':
        result['date_scope']='Retrieval time; publication date and active request not verified'
        result['search_query']=raw.get('search_query')
    if raw['kind']=='job_posting':
        result['job_type']=raw.get('job_type')
        result['date_scope']=raw.get('date_scope','Source publication timestamp')
        result['source_attribution']=raw.get('source_attribution',raw['source'])
    measurement=raw.get('measurement')
    if measurement:
        value=measurement.get('value')
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError('Invalid source measurement')
        result['measurement']={'value':value,'unit':measurement.get('unit'),
            'scope':'Original source metric; normalized attention is not buyer count'}
    comparison = raw.get('comparison')
    if comparison:
        # Never compare search-index changes to job counts or incompatible windows.
        a, b = comparison.get('previous'), comparison.get('current')
        if (type(a) not in (int,float) or type(b) not in (int,float) or not all(math.isfinite(x) and x>=0 for x in (a,b))
            or comparison.get('unit') not in ('request_count','job_count','normalized_search_index')
            or type(comparison.get('window_days')) is not int or comparison['window_days']<1
            or observed(comparison['previous_end']) >= observed(comparison['current_end'])
            or observed(comparison['current_end']) > now):
            raise ValueError('Comparable observed measurements required')
        result['comparison'] = {**comparison, 'change_percent': round((b-a)/a*100,2) if a>0 else None,
            'scope': 'This source and equal-duration windows only; not total market growth'}
    return result


def collect(rows, now=None, max_age_days=30):
    now = now or datetime.now(timezone.utc)
    if not isinstance(rows,list) or len(rows)>1000: raise ValueError('At most 1000 observations per run')
    result, seen, seen_urls = [], set(), set()
    for raw in rows:
        item=normalize(raw,now,max_age_days)
        if item and item['id'] not in seen and item['url'] not in seen_urls:
            seen.add(item['id']); seen_urls.add(item['url']); result.append(item)
    return result
