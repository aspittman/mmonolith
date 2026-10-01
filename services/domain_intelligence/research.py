"""Evidence-first domain discovery. Numeric legacy scores never select candidates."""
from datetime import datetime, timezone
from itertools import product
from statistics import median
from uuid import UUID, uuid5, NAMESPACE_URL
import re
from devspace_domain_research.grammar import analyze_grammar
from devspace_domain_research.market_data import valuation_eligible, parse_date
from devspace_domain_research.sales_sources import canonicalize_sales
from devspace_domain_research.scorer import score_domain
from .providers import number

CONTRACT='domain-evidence-v1'


def valid_domain(value):
    value=str(value).strip().lower()
    if not re.fullmatch(r'(?!-)[a-z0-9-]{1,63}(?<!-)\.[a-z]{2,24}',value):
        raise ValueError('Expected an ASCII second-level domain')
    return value


def observed_candidates(sales,niche,keywords,locations,retail,limit=50,minimum_support=2):
    """Recombine observed template tokens; optional geo hypothesis needs keyword sales.

    This deliberately does not call the preserved heuristic candidate generator.
    Every output carries its generation basis, which is a hypothesis, not a valuation.
    """
    candidates={}
    sold={r['domain'] for r in sales}
    grammar=analyze_grammar(sales,niche)
    templates=sorted(grammar['templates'],key=lambda r:(-r['sale_count'],r['template']))
    for row in templates:
        if row['sale_count']<minimum_support: continue
        choices=[sorted(row['slot_values'].get(str(i),{}))[:8] for i in range(len(row['slots']))]
        for tokens in product(*choices):
            for extension in sorted(row['extensions']):
                domain=''.join(tokens)+'.'+extension
                try: domain=valid_domain(domain)
                except ValueError: continue
                if domain in sold: continue
                candidates.setdefault(domain,{'domain':domain,'generation_basis':{'type':'observed_sales_template',
                    'template':row['template'],'supporting_sale_count':row['sale_count'],
                    'representative_sales':row['representative_sales']}})
                if len(candidates)>=limit: return list(candidates.values())
    for keyword in keywords:
        # Keyword placement statistics support only the general naming hypothesis.
        stats=next((r for r in retail if r['keyword']==keyword.lower()),None)
        if not stats or number(stats['placements']['end']['sale_count'],True)==0: continue
        for location in locations:
            term=re.sub('[^a-z0-9]','',location.lower())
            word=re.sub('[^a-z0-9]','',keyword.lower())
            if not term or not word: continue
            domain=valid_domain(term+word+'.com')
            if domain in sold: continue
            candidates.setdefault(domain,{'domain':domain,'generation_basis':{'type':'geo_keyword_hypothesis',
                'keyword':keyword,'location':location,'source_url':stats['source_url'],
                'note':'Keyword-ending sales exist; this does not prove demand for this geography or domain.'}})
            if len(candidates)>=limit: return list(candidates.values())
    return list(candidates.values())


def build_research(org,run_key,niche,keywords,locations,sales,retail=None,demand=None,availability=None,
                   buyers=None,candidates=None,context=None,is_test=False,legacy=False,at=None,limit=50,failures=None,performance=None,assessments=None):
    UUID(org)
    if not run_key or not keywords: raise ValueError('Run key and explicit research keywords required')
    at=at or datetime.now(timezone.utc); context=context or {}; retail=retail or []; availability=availability or {}
    if any(row.get('organization_id')!=org for rows in context.values() for row in rows):
        raise ValueError('Mixed-tenant context rejected')
    subject=niche+'|'+','.join(sorted(locations)) if locations else niche
    # Quarantine/exclusion already performed by the existing importers. Avoid future
    # transactions, asking prices, mixed currencies and unrelated keyword/niche rows.
    eligible=[s for s in canonicalize_sales(sales)['records'] if valuation_eligible(s,'USD',3)
        and parse_date(s['sale_date'])<=at.date() and (at.date()-parse_date(s['sale_date'])).days<=1825
        and any(re.sub('[^a-z0-9]','',k.lower()) in s['domain'].split('.')[0] for k in keywords)]
    discovered=observed_candidates(eligible,niche,keywords,locations,retail,limit)
    by_domain={}
    for domain in candidates or []:
        domain=valid_domain(domain)
        by_domain.setdefault(domain,{'domain':domain,'generation_basis':{'type':'user_supplied_research_seed'}})
    for row in discovered: by_domain.setdefault(row['domain'],row)
    if len(by_domain)>limit: by_domain=dict(list(by_domain.items())[:limit])
    buyer_rows=[]
    if buyers:
        if buyers.get('organization_id')!=org or buyers.get('subject_key')!=subject:
            raise ValueError('Buyer evidence must match organization and subject')
        if not buyers.get('source_url') or not buyers.get('retrieved_at'):
            raise ValueError('Buyer evidence needs provenance')
        # These are observed matching businesses, not an estimate of the whole market.
        unique={str(b.get('domain','')).lower():b for b in buyers['companies'] if b.get('domain') and b.get('fit_reason')}
        buyer_rows=list(unique.values())
    # CRM outcomes are internal execution evidence. Keep them separate from
    # external comparables and demand measurements.
    portfolio={r.get('domain'):r for r in (performance or {}).get('rows', [])}
    for row in by_domain.values():
        domain=row['domain']; extension=domain.rsplit('.',1)[1]
        comps=[s for s in eligible if s['domain']!=domain and s['domain'].rsplit('.',1)[1]==extension]
        # Factual filter, no similarity or brand-score threshold. Surface match criteria.
        comps=sorted(comps,key=lambda s:(s['sale_date'],s['domain']),reverse=True)
        prices=[s['sale_price'] for s in comps]
        row.update({'niche':niche,'subject_key':subject,'research_owner':'mmonolith',
            'comparables':[{'domain':s['domain'],'sale_price':s['sale_price'],'currency':s['currency'],
              'sale_date':s['sale_date'],'marketplace':s.get('marketplace'),'source':s['source_name'],
              'source_url':s.get('source_url'),'transaction_type':s['transaction_type']} for s in comps[:50]],
            'comparable_count':len(comps),'comparable_median':median(prices) if prices else None,
            'comparable_min':min(prices) if prices else None,'comparable_max':max(prices) if prices else None,
            'comparable_filter':'Same extension, explicit research keyword, USD, reported sales within five years. Not a predicted sale price.',
            'currency':'USD','availability':availability.get(domain,{'status':'unknown','provider':'unconfigured'}),
            'potential_buyers':buyer_rows,'potential_buyer_count':len(buyer_rows) if buyers else None,
            'buyer_evidence':{k:buyers[k] for k in ('source_url','retrieved_at')} if buyers else None,
            'keyword_demand':demand,'retail_keyword_statistics':retail,
            'internal_performance':({'source':'crm_outreach_performance','observed_at':at.isoformat(),
              'sent':int(portfolio[domain].get('sent') or 0),
              'positive_responses':int(portfolio[domain].get('positive_responses') or 0),
              'negative_responses':int(portfolio[domain].get('negative_responses') or 0),
              'sale_price':portfolio[domain].get('sale_price'),
              'gross_profit':portfolio[domain].get('gross_profit')}
              if domain in portfolio else None),
            'missing_evidence':[]})
        if not comps: row['missing_evidence'].append('No individual comparable sales')
        if not demand: row['missing_evidence'].append('No keyword demand measurements')
        if buyers is None: row['missing_evidence'].append('No verified potential-buyer sample')
        if row['availability'].get('status')=='unknown': row['missing_evidence'].append('Availability not checked')
        if row['availability'].get('acquisition_price') is None: row['missing_evidence'].append('Acquisition price unknown')
        if domain in (assessments or {}):
            row.update({k:v for k,v in assessments[domain].items() if k in ('decision_metrics','trademark_screening')})
        if legacy:
            old=score_domain(domain,niche)
            row['legacy_comparison']={'label':'Legacy heuristic; not measured market evidence',
              'score':old['score'],'resale_likelihood_score':old['resale_likelihood_score'],
              'target_price':old['target_price']}
    reports=[r for r in context.get('intelligence_reports',[]) if r.get('subject_key')==subject and r.get('is_test',False)==is_test]
    previous=max(reports,key=lambda r:r['created_at']) if reports else None
    report_ids={r['id'] for r in reports}
    evaluations=[f for f in context.get('feedback_evaluations',[]) if f['intelligence_report_id'] in report_ids]
    outcomes=[r for r in context.get('execution_results',[]) if r['subject_key']==subject and r.get('results',{}).get('is_test',False)==is_test]
    # Evidence sufficiency indicator, not probability of selling. No opportunity score.
    coverage=sum(bool(v) for v in (eligible,demand,buyer_rows,any(r.get('status')!='unknown' for r in availability.values())))/4
    confidence=round((len(eligible)/(len(eligible)+3))*coverage,6)
    if evaluations:
        latest={f['execution_result_id']:f for f in sorted(evaluations,key=lambda f:f['created_at']) if f['evaluation']!='INSUFFICIENT_DATA'}
        if latest:
            changes=[max(-.05,min(.05,float(f['confidence_after'])-float(f['confidence_before'])))*f['sample_size']/(f['sample_size']+100) for f in latest.values()]
            confidence=round(max(0,min(1,confidence+sum(changes)/len(changes))),6)
    return {'report':{'run_key':run_key,'subject_key':subject,'subject_type':'domain_market','report_type':'DOMAIN_MARKET',
      'summary':f'{niche}: {len(eligible)} reported sales and {len(by_domain)} research candidates. Missing data remains unknown; no resale forecast.',
      'overall_score':None,'confidence_score':confidence,'previous_report_id':previous['id'] if previous else None,
      'correlation_id':previous['correlation_id'] if previous else str(uuid5(NAMESPACE_URL,org+':'+run_key)),
      'is_test':is_test,'metadata':{'research_contract':CONTRACT,'research_owner':'mmonolith','observed_at':at.isoformat(),
        'niche':niche,'keywords':keywords,'locations':locations,'candidates':list(by_domain.values()),
        'reported_sales_count':len(eligible),'retail_keyword_statistics':retail,'keyword_demand':demand,
        'confidence_method':'Individual sales n/(n+3) × observed coverage across sales, demand, buyers and availability; not sale probability.',
        'follow_up_evidence_gaps':sorted({gap for result in outcomes if result.get('results',{}).get('review_contract')=='domain-evidence-review-v1' for finding in result['results'].get('findings',[]) for gap in finding.get('missing_evidence',[])}),
        'internal_outcomes':outcomes,'feedback_evaluations':evaluations,'provider_failures':failures or [],
        'limitations':['Reported sales are selection-biased; sell-through probability needs unsold inventory and exposure time.',
          'Domain candidates are hypotheses. Legacy scores are optional comparisons, not evidence.']}},
      'signals':[],'predictions':[],'feedback_ids':[f['id'] for f in evaluations]}
