"""Research technical service demand from explicit attributed sources."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import UUID
from dotenv import dotenv_values
from services.shared.outbox import Outbox
from services.shared.supabase import ClientResearchSupabase
from .pipeline import build_bundle
from .sources import google_play_observations, trend_observations, upwork_observations, search_observations, job_observations

from .research_sources import export_observations, technical_observations, reddit_observations, SOURCE_SET

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--organization',required=True)
    parser.add_argument('--run-key',required=True)
    parser.add_argument('--observations',type=Path)
    parser.add_argument('--google-play',type=Path)
    parser.add_argument('--trends',type=Path)
    parser.add_argument('--upwork',type=Path)
    for source in ('reddit','fiverr','github-issues','stack-overflow','job-boards'):
        parser.add_argument('--'+source+'-export',type=Path)
    for source in ('reddit','github-issues','stack-overflow'):
        parser.add_argument('--'+source,action='store_true')
    parser.add_argument('--search',action='store_true')
    parser.add_argument('--jobs',action='store_true')
    parser.add_argument('--max-queries',type=int,default=8)
    parser.add_argument('--technical-max-queries',type=int,default=2)
    parser.add_argument('--configuration',type=Path)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    org=str(UUID(args.organization))
    if not args.run_key or len(args.run_key)>160: parser.error('Run key must have 1–160 characters')
    if not any((args.observations,args.google_play,args.trends,args.upwork,args.search,args.jobs,args.reddit,args.github_issues,args.stack_overflow,
        args.reddit_export,args.fiverr_export,args.github_issues_export,args.stack_overflow_export,args.job_boards_export)):
        parser.error('Choose at least one real source; fixture data is not used automatically')
    configuration=json.loads(args.configuration.read_text()) if args.configuration else {}
    root=ROOT/'data/devspace_services'/org; root.mkdir(parents=True,exist_ok=True)
    outbox=Outbox(root/'publications.sqlite3')
    key='devspace_services:'+args.run_key
    saved=outbox.get('devspace_services',org,key)
    client=None
    if args.publish:
        env=dotenv_values(ROOT.parent/'devspace-crm/.env.local')
        client=ClientResearchSupabase(env['NEXT_PUBLIC_SUPABASE_URL'],env['SUPABASE_SERVICE_ROLE_KEY'],'devspace_services')
        if not client.enabled_profiles(org): raise ValueError('DevSpace Services must be enabled for this organization')
    if saved:
        bundle,record_id=saved
        if bundle['report']['metadata']['configuration']!=configuration: raise ValueError('Run key configuration mismatch')
    else:
        observations=[]
        failures=[]
        coverage={source:{'status':'UNCONFIGURED','collected':0} for source in SOURCE_SET}
        for source in ('reddit','fiverr','github_issues','stack_overflow','job_boards'):
            path=getattr(args,source+'_export')
            if path:
                found=export_observations(path,source,org); observations.extend(found)
                coverage[source]={'status':'COLLECTED','collected':len(found),'method':'authorized_export'}
        for source in ('reddit','github_issues','stack_overflow'):
            if getattr(args,source):
                try:
                    found=reddit_observations(args.technical_max_queries) if source=='reddit' else technical_observations(source,args.technical_max_queries)
                    observations.extend(found)
                    coverage[source]={'status':'COLLECTED','collected':len(found),'method':'public_api_or_rss'}
                except (RuntimeError,ValueError):
                    failures.append({'source':source,'reason':'Collection failed; no evidence invented'})
                    coverage[source]={'status':'FAILED','collected':0}

        if args.observations:
            payload=json.loads(args.observations.read_text())
            if payload.get('organization_id')!=org: raise ValueError('Observation export organization mismatch')
            observations.extend(payload['observations'])
        if args.google_play: observations.extend(google_play_observations(json.loads(args.google_play.read_text())))
        if args.trends: observations.extend(trend_observations(json.loads(args.trends.read_text())))
        if args.upwork: observations.extend(upwork_observations(args.upwork))
        if args.jobs:
            try: observations.extend(job_observations())
            except RuntimeError:
                failures.append({'source':'remotive','reason':'Job feed unavailable'})
        if args.search:
            env=dotenv_values(ROOT.parent/'devspace-one/.env')
            if not (os.getenv('SERPAPI_API_KEY') or os.getenv('SERP_API_KEY')):
                os.environ['SERP_API_KEY']=env.get('SERP_API_KEY','')
            try: observations.extend(search_observations(args.max_queries,failures))
            except RuntimeError:
                failures.append({'source':'public_search','reason':'No search evidence collected'})
        bundle=build_bundle(org,observations,configuration,client.context(org) if client else {},args.run_key)
        for source, enabled, label in [('upwork',args.upwork,'upwork'),('google_play',args.google_play,'google_play'),
            ('google_trends',args.trends,'google_trends'),('job_boards',args.jobs,'remotive'),('public_search',args.search,'public_search')]:
            if enabled:
                count=sum(e.get('kind')=='search_interest' if source=='google_trends' else e['source']==label for e in observations)
                failed=any(f.get('source')==label or (label=='public_search' and 'query' in f) for f in failures)
                coverage[source]={'status':'PARTIAL' if failed and count else 'FAILED' if failed else 'COLLECTED','collected':count}
        bundle['report']['metadata']['source_connectors']=coverage
        bundle['report']['metadata']['provider_failures']=failures
        bundle['report']['metadata']['collection_status']='PARTIAL' if failures else 'COMPLETE'
        if not bundle['report']['metadata']['evidence']: raise ValueError('No fresh real observations; report was not published')
        bundle=outbox.save('devspace_services',org,key,bundle); record_id=None
    if args.publish and record_id is None:
        record_id=client.publish(org,bundle)
        outbox.acknowledge('devspace_services',org,key,record_id)
    path=root/'latest_report.json'; temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(bundle,indent=2)); temp.replace(path)
    print(json.dumps({'service_id':'devspace_services','report_path':str(path),'intelligence_report_id':record_id,
        'ranked_services':[{'service':o['name'],'research_strength_score':o['research_strength_score'],
            'buyer_requests':o['explicit_requests'],'job_postings':o['job_postings'],
            'web_mentions':o['web_mentions'],'app_pain_mentions':o['app_pain_mentions']}
            for o in bundle['report']['metadata']['opportunities']]}))


if __name__=='__main__':
    main()
