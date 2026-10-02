"""Shared research CLI for product-backed workloads; no profiles or execution."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import UUID
from dotenv import dotenv_values
import requests
from .product_research import build_bundle, public_url
from .outbox import Outbox
from .supabase import ClientResearchSupabase

ROOT=Path(__file__).resolve().parents[2]
QUERIES={
 'scholarship_research':['international scholarships official eligibility deadline','global undergraduate scholarships application requirements'],
 'investor_research':['venture capital global seed investment criteria official','international startup accelerator funding application criteria']}


def discover(service):
    key=os.getenv('SERPAPI_API_KEY') or os.getenv('SERP_API_KEY')
    if not key: raise ValueError('Discovery provider credential is missing')
    rows=[];failures=[]
    for query in QUERIES[service]:
        try:
            response=requests.get('https://serpapi.com/search.json',params={'engine':'google','api_key':key,'q':query,'num':10},timeout=20,allow_redirects=False)
            if response.status_code!=200: raise RuntimeError('Discovery rejected')
            body=response.json()
            if body.get('error'): raise RuntimeError('Discovery unavailable')
            for result in body.get('organic_results',[])[:10]:
                try:url=public_url(result.get('link',''))
                except ValueError:continue
                rows.append({'name':result.get('title') or url,'program_id':sha256(url.encode()).hexdigest()[:24],
                    'url':url,'is_test':False})
        except (requests.RequestException,ValueError,RuntimeError):
            failures.append({'source':'public_search','reason':'Discovery query failed; details withheld'})
    return rows,failures


def main(service):
    parser=argparse.ArgumentParser(description='Global sourced research; profile matching belongs to Decision Engine.')
    parser.add_argument('--organization',required=True)
    parser.add_argument('--run-key',required=True)
    parser.add_argument('--source-export',type=Path)
    parser.add_argument('--issuer-domains',nargs='*',default=[])
    parser.add_argument('--discover',action='store_true')
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args();org=str(UUID(args.organization))
    if not args.source_export and not args.discover:parser.error('Select a live source export or discovery')
    if not 1<=len(args.run_key)<=160:parser.error('Run key must have 1–160 characters')
    folder=ROOT/'data'/service/org;folder.mkdir(parents=True,exist_ok=True)
    outbox=Outbox(folder/'publications.sqlite3');key=service+':'+args.run_key
    configuration={'issuer_domains':sorted(args.issuer_domains),'discover':args.discover,
        'export_sha256':sha256(args.source_export.read_bytes()).hexdigest() if args.source_export else None}
    saved=outbox.get(service,org,key);client=None
    if args.publish:
        env=dotenv_values(ROOT.parent/'devspace-crm/.env.local')
        client=ClientResearchSupabase(env['NEXT_PUBLIC_SUPABASE_URL'],env['SUPABASE_SERVICE_ROLE_KEY'],service)
        if not client.enabled_profiles(org):raise ValueError('Organization research service is not enabled')
    if saved:
        bundle,record_id=saved
        if bundle['report']['metadata'].get('research_configuration')!=configuration:raise ValueError('Run key research configuration mismatch')
    else:
        rows=[];failures=[]
        if args.source_export:
            payload=json.loads(args.source_export.read_text())
            if payload.get('organization_id')!=org or payload.get('service_id')!=service or payload.get('is_test') is not False:
                raise ValueError('Live export tenant/service mismatch')
            rows.extend(payload['opportunities'])
        if args.discover:
            one=dotenv_values(ROOT.parent/'devspace-one/.env')
            if not (os.getenv('SERPAPI_API_KEY') or os.getenv('SERP_API_KEY')):os.environ['SERP_API_KEY']=one.get('SERP_API_KEY','')
            found,failures=discover(service);rows.extend(found)
        bundle=build_bundle(service,org,rows,args.issuer_domains,args.run_key)
        bundle['report']['metadata']['research_configuration']=configuration
        bundle['report']['metadata']['provider_failures'].extend(failures)
        if failures:bundle['report']['metadata']['collection_status']='PARTIAL'
        if not bundle['report']['metadata']['opportunities']:raise ValueError('No source opportunities collected; publication skipped')
        bundle=outbox.save(service,org,key,bundle);record_id=None
    if args.publish and record_id is None:
        record_id=client.publish(org,bundle);outbox.acknowledge(service,org,key,record_id)
    path=folder/'latest_report.json';temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(bundle,indent=2,allow_nan=False));temporary.replace(path)
    print(json.dumps({'service_id':service,'report_path':str(path),'intelligence_report_id':record_id,
        'opportunities':len(bundle['report']['metadata']['opportunities']),
        'issuer_verified':sum(o['source_status']=='ISSUER_PAGE_VERIFIED' for o in bundle['report']['metadata']['opportunities']),
        'collection_status':bundle['report']['metadata']['collection_status']}))
