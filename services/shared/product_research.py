"""Source intelligence for products. Matching and execution belong to other engines."""
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlparse, urlunparse
from uuid import UUID, uuid5, NAMESPACE_URL
import html
import ipaddress
import json
import math
import re
import socket
import requests

SERVICES={'scholarship_research':'SCHOLARSHIP_RESEARCH','investor_research':'INVESTOR_RESEARCH'}
PROFILE_FIELDS={
 'scholarship_research':{'residence_country','residence_region','citizenship','field_of_study','study_level','gpa','age','financial_need'},
 'investor_research':{'industry','stage','country','region','business_model','funding_amount','currency','annual_revenue'}}
FACT_FIELDS={
 'scholarship_research':{'deadline','deadline_type','award_min','award_max','currency','requirements_complete','application_url','accepting_applications'},
 'investor_research':{'deadline','deadline_type','check_min','check_max','currency','mandate_complete','application_url','last_investment_date','accepting_applications','portfolio_companies','recent_investments','current_activity'}}


def timestamp(value):
    date=datetime.fromisoformat(value.replace('Z','+00:00'))
    if date.tzinfo is None: raise ValueError('Timezone-aware source date required')
    return date.astimezone(timezone.utc)


def public_url(value):
    parsed=urlparse(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Public HTTPS source required')
    host=parsed.hostname.lower()
    if host=='localhost' or '.' not in host or host.endswith(('.local','.internal')): raise ValueError('Public issuer host required')
    try:
        if not ipaddress.ip_address(host).is_global: raise ValueError('Private source address rejected')
    except ValueError as exc:
        if 'Private source' in str(exc): raise
    return urlunparse(('https',parsed.netloc.lower(),parsed.path or '/',parsed.params,parsed.query,''))


def source_text(url, domains):
    url=public_url(url);host=urlparse(url).hostname
    if host not in domains: raise ValueError('Issuer domain is not configured as authoritative')
    # Check DNS before a bounded fetch; redirects are deliberately not followed.
    addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Non-public issuer address rejected')
    try:
        response=requests.get(url,headers={'User-Agent':'DevSpaceProductResearch/1.0'},timeout=20,
            allow_redirects=False,stream=True)
        with response:
            if response.status_code!=200: raise RuntimeError('Issuer source unavailable')
            if 'text/' not in response.headers.get('Content-Type',''): raise RuntimeError('Unsupported issuer source format')
            chunks=[]; size=0
            for chunk in response.iter_content(65536):
                size+=len(chunk)
                if size>2_000_000: raise RuntimeError('Issuer page exceeds collection bound')
                chunks.append(chunk)
            content=b''.join(chunks).decode(response.encoding or 'utf-8',errors='replace')
    except requests.RequestException: raise RuntimeError('Issuer transport failed') from None
    content=re.sub(r'<(script|style)\b[^>]*>.*?</\1>',' ',content,flags=re.S|re.I)
    return ' '.join(html.unescape(re.sub('<[^>]+>',' ',content)).split())


def value_valid(field,value, service):
    if field in ('deadline','last_investment_date'):
        timestamp(value)
    elif field in ('award_min','award_max','check_min','check_max','gpa','age','funding_amount','annual_revenue'):
        if type(value) not in (int,float) or not math.isfinite(value) or value<0: raise ValueError('Invalid numeric fact')
    elif field in ('requirements_complete','mandate_complete','accepting_applications','financial_need'):
        if type(value) is not bool: raise ValueError('Explicit boolean fact required')
    elif field=='application_url': public_url(value)
    elif field=='deadline_type':
        if value not in ('fixed','rolling'): raise ValueError('Invalid deadline type')
    elif field=='currency':
        if not isinstance(value,str) or not re.fullmatch('[A-Z]{3}',value): raise ValueError('Currency code required')
    elif not isinstance(value,(str,list)) or not value: raise ValueError('Nonempty fact required')


def build_bundle(service, org, rows, domains, run_key, *, now=None, reader=source_text):
    if service not in SERVICES: raise ValueError('Unknown product research service')
    org=str(UUID(org));now=now or datetime.now(timezone.utc)
    if not isinstance(rows,list) or len(rows)>250: raise ValueError('At most 250 research candidates per run')
    domains={d.lower().strip() for d in domains}; pages={}; failures=[]; records={}
    for raw in rows:
        if raw.get('is_test') is not False: raise ValueError('Explicit live research declaration required')
        url=public_url(raw['url']);host=urlparse(url).hostname
        name=raw.get('name');program=raw.get('program_id')
        if not isinstance(name,str) or not name.strip() or not isinstance(program,str) or not program.strip():
            raise ValueError('Source name and stable program identity required')
        category=raw.get('opportunity_type','SCHOLARSHIP' if service=='scholarship_research' else 'INVESTOR')
        allowed={'SCHOLARSHIP'} if service=='scholarship_research' else {'INVESTOR','VC_FIRM','ANGEL','ACCELERATOR','FUNDING_PROGRAM'}
        if category not in allowed: raise ValueError('Opportunity belongs to a different service')
        key=sha256((host+':'+program).encode()).hexdigest()[:24]
        item={'id':key,'name':name[:300],'program_id':program,'opportunity_type':category,'url':url,
            'source_status':'UNVERIFIED','verified_at':None,'facts':{},'criteria':[],
            'normalization_reviewed':raw.get('normalization_reviewed') is True,
            'status':'RESEARCH_FURTHER','coverage':'global','limitations':[]}
        if host in domains:
            if url not in pages:
                try: pages[url]=reader(url,domains)
                except (RuntimeError,ValueError,OSError):
                    pages[url]=None;failures.append({'source_url':url,'reason':'Issuer verification failed'})
            page=pages[url]
            if page:
                def supported(claim):
                    quote=claim.get('quote'); claim_url=public_url(claim.get('source_url',url))
                    if claim_url!=url or not isinstance(quote,str) or len(quote.strip())<8:
                        raise ValueError('Each fact needs a quotation from this issuer page')
                    normalized=' '.join(quote.split())
                    if normalized not in page: raise ValueError('Source quotation could not be verified')
                    return {'value':claim['value'],'quote':normalized,'source_url':url,'verified_at':now.isoformat()}
                for field,claim in raw.get('facts',{}).items():
                    if field not in FACT_FIELDS[service]: raise ValueError('Unsupported research fact')
                    value_valid(field,claim['value'],service)
                    item['facts'][field]=supported(claim)
                for criterion in raw.get('criteria',[]):
                    field=criterion['field'];op=criterion['operator']
                    if field not in PROFILE_FIELDS[service] or op not in ('in','eq','gte','lte'):
                        raise ValueError('Unsupported eligibility or fit criterion')
                    value=criterion['value']
                    if op=='in':
                        if not isinstance(value,list) or not value or any(not isinstance(v,str) for v in value): raise ValueError('Allowed values required')
                    else: value_valid(field,value,service)
                    item['criteria'].append({**supported(criterion),'field':field,'operator':op,'required':True})
                for low,high in [('award_min','award_max'),('check_min','check_max')]:
                    if low in item['facts'] and high in item['facts'] and item['facts'][low]['value']>item['facts'][high]['value']:
                        raise ValueError('Inverted monetary range')
                item.update(source_status='ISSUER_PAGE_VERIFIED',verified_at=now.isoformat(),status='CURRENT')
                deadline=item['facts'].get('deadline')
                if deadline and timestamp(deadline['value'])<=now: item['status']='EXPIRED'
                if not item['criteria']:item['limitations'].append('Eligibility or investment mandate not extracted')
        if item['source_status']=='UNVERIFIED':item['limitations'].append('Discovery lead only; authoritative issuer verification required')
        # Conflicting same-program exports require review, never silently pick a winner.
        if key in records and (records[key]['facts']!=item['facts'] or records[key]['criteria']!=item['criteria']):
            records[key]['status']='SOURCE_CONFLICT';records[key]['limitations'].append('Conflicting duplicate facts require re-research')
        else:records.setdefault(key,item)
    opportunities=list(records.values())
    return {'report':{'run_key':service+':'+run_key,'subject_key':service+':global','subject_type':'product_opportunities',
        'report_type':SERVICES[service],'summary':f'{len(opportunities)} global candidates; issuer verification and profile matching are separate.',
        'correlation_id':str(uuid5(NAMESPACE_URL,org+':'+service+':'+run_key)),
        'overall_score':None,'confidence_score':round(sum(o['source_status']=='ISSUER_PAGE_VERIFIED' and o['normalization_reviewed'] for o in opportunities)/len(opportunities),3) if opportunities else 0,'is_test':False,
        'metadata':{'service_id':service,'research_contract':'product-research-v1','coverage':'global',
            'opportunities':opportunities,'provider_failures':failures,'collection_status':'PARTIAL' if failures else 'COMPLETE',
            'confidence_scope':'Fraction of batch records with verified issuer pages and reviewed normalization; not user fit or outcome probability',
            'profile_matching_performed':False,'execution_authorized':False,
            'limitations':['Source quotations are verified; normalized interpretations require review.',
                'Missing criteria, deadlines, amounts and activity remain unknown.',
                'Discovery leads do not establish availability, eligibility or investor interest.']}},
        'signals':[],'predictions':[],'feedback_ids':[]}
