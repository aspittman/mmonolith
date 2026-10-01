"""Research domain candidates from attributed facts; never purchase or send outreach."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import UUID
from devspace_domain_research.sales_importer import import_configured_sources
from devspace_domain_research.market_data import load_sales
from devspace_domain_research.availability import StaticFileAvailabilityChecker
from .client import LoopClient
from .providers import EvidenceCache, NameBioRetailProvider, KeywordDemandProvider, NamecheapAvailabilityProvider
from .research import build_research


def main():
    from dotenv import load_dotenv
    load_dotenv()
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--organization',required=True)
    p.add_argument('--run-key',required=True)
    p.add_argument('--niche',required=True)
    p.add_argument('--keyword',action='append',required=True)
    p.add_argument('--location',action='append',default=[])
    p.add_argument('--candidate',action='append',default=[])
    p.add_argument('--namebio-file'); p.add_argument('--dnjournal-file'); p.add_argument('--sales-file')
    p.add_argument('--namebio-live',action='store_true',help='Call free NameBio keyword statistics; cached 24h, rate limited')
    p.add_argument('--with-keywords',action='store_true',help='Explicitly enable billed DataForSEO keyword lookup')
    p.add_argument('--demand-file',help='Previously collected keyword provider envelope')
    p.add_argument('--retail-file',help='Previously collected NameBio provider envelope or list')
    p.add_argument('--quote-file',help='Organization-scoped GoDaddy checkout quote export')
    p.add_argument('--assessment-file',help='Attributed optional normalized decision dimensions')
    p.add_argument('--availability-file'); p.add_argument('--buyers-file')
    p.add_argument('--registrar-check',action='store_true',help='Read-only Namecheap availability; requires configured credentials')
    p.add_argument('--legacy-comparison',action='store_true')
    p.add_argument('--sync-crm',action='store_true')
    p.add_argument('--limit',type=int,default=50)
    p.add_argument('--output-dir',default='data/processed/domain_intelligence')
    p.add_argument('--cache',default='data/domain_evidence.sqlite3')
    args=p.parse_args(); UUID(args.organization)
    if not 1<=args.limit<=50: p.error('--limit must be 1–50')
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    root=Path(args.output_dir);root.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256((args.organization+':'+args.run_key).encode()).hexdigest()
    path=root/(key+'.json')
    client=LoopClient(os.environ['CRM_BASE_URL'],os.environ['BOT_API_SECRET']) if args.sync_crm else None
    if path.exists():
        bundle=json.loads(path.read_text())
        if bundle['report']['is_test']!=(os.getenv('DEVSPACE_ENV')=='test'): raise ValueError('Run mode differs; use a new run key')
    else:
        cache=EvidenceCache(args.cache); failures=[]
        def collect(label,fn):
            try: return fn()
            except Exception as error:
                # No exception bodies: provider errors can contain authentication/query data.
                failures.append({'provider':label,'error_type':type(error).__name__})
                logging.warning('%s unavailable (%s); continuing with missing evidence',label,type(error).__name__)
                return None
        sales=import_configured_sources(args.namebio_file,args.dnjournal_file)
        records=sales['records']
        if sales['warnings']: failures.append({'provider':'sales_import','error_type':'ImportWarning'})
        if args.sales_file:
            loaded=load_sales(args.sales_file)
            if loaded['error']: raise ValueError('Sales input cannot be read')
            records+=loaded['records']
        retail=[]
        if args.retail_file:
            loaded=json.loads(Path(args.retail_file).read_text());retail=loaded if isinstance(loaded,list) else [loaded]
        if args.namebio_live:
            provider=NameBioRetailProvider(cache)
            for keyword in args.keyword:
                evidence=collect('NameBio',lambda:provider.fetch(keyword,wait=True))
                if evidence: retail.append(evidence)
        demand=json.loads(Path(args.demand_file).read_text()) if args.demand_file else None
        if args.with_keywords:
            demand=collect('DataForSEO',lambda:KeywordDemandProvider(cache,os.environ['DATAFORSEO_LOGIN'],os.environ['DATAFORSEO_PASSWORD'],
                int(os.getenv('DATAFORSEO_LOCATION_CODE','2840')),os.getenv('DATAFORSEO_LANGUAGE_CODE','en')).fetch(args.keyword))
        buyers=json.loads(Path(args.buyers_file).read_text()) if args.buyers_file else None
        context=client.context(args.organization) if client else {}
        performance=collect('CRMOutreachPerformance',lambda:client.performance(args.organization)) if client and os.getenv('DEVSPACE_ENV')!='test' else None
        from .authorized_inputs import quotes, assessments
        subject=args.niche+'|'+','.join(sorted(args.location)) if args.location else args.niche
        assessment_rows=assessments(args.assessment_file,args.organization,subject) if args.assessment_file else None
        options=dict(assessments=assessment_rows,org=args.organization,run_key=args.run_key,niche=args.niche,keywords=args.keyword,locations=args.location,
          sales=records,retail=retail,demand=demand,buyers=buyers,candidates=args.candidate,context=context,
          is_test=os.getenv('DEVSPACE_ENV')=='test',legacy=args.legacy_comparison,limit=args.limit,failures=failures,
          performance=performance)
        bundle=build_research(**options)
        domains=[r['domain'] for r in bundle['report']['metadata']['candidates']]
        availability={}
        if args.availability_file: availability=StaticFileAvailabilityChecker(args.availability_file).check(domains)
        if args.registrar_check and domains:
            fetched=collect('Namecheap',lambda:NamecheapAvailabilityProvider(cache,os.environ['NAMECHEAP_API_USER'],
              os.environ['NAMECHEAP_API_KEY'],os.environ.get('NAMECHEAP_USERNAME',os.environ['NAMECHEAP_API_USER']),
              os.environ['NAMECHEAP_CLIENT_IP']).fetch(domains))
            if fetched: availability=fetched
        if args.quote_file:
            availability.update(quotes(args.quote_file,args.organization,subject,domains))
        bundle=build_research(**options,availability=availability)
        temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(bundle,indent=2,allow_nan=False));temporary.replace(path)
    report_id=client.publish(args.organization,bundle) if client else None
    print(json.dumps({'organization_id':args.organization,'intelligence_report_id':report_id,'path':str(path),
      'candidates':len(bundle['report']['metadata']['candidates']),'reported_sales':bundle['report']['metadata']['reported_sales_count'],
      'provider_failures':bundle['report']['metadata']['provider_failures']}))

if __name__=='__main__': main()
