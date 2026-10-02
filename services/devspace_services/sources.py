"""Explicit import adapters; fixtures never become live evidence implicitly."""
from .google_play.providers import niches_from_payload
import csv
from datetime import datetime, timezone
from hashlib import sha256
import os
import requests
import html
import re
import json
from pathlib import Path
from .catalog import SERVICES


def google_play_observations(payload):
    if payload.get('demo_data') is not False: raise ValueError('Live Google Play export required')
    rows=[]
    for niche in niches_from_payload(payload,100):
        for app in niche.apps:
            if app.evidence_type == 'inferred': continue
            for review in app.reviews:
                if review.rating>3 or not review.date: continue
                rows.append({'kind':'review_pain','source':'google_play', 'record_id':app.package_name+':'+review.review_id,
                    'url': app.play_url+'?reviewId='+review.review_id if '?' not in app.play_url else app.play_url+'&reviewId='+review.review_id,
                    'observed_at':review.date, 'text':review.text, 'is_test':False})
    return rows


def trend_observations(payload):
    if payload.get('demo_data') is not False: raise ValueError('Live trend export required')
    rows=[]
    for signal in [payload,*payload.get('signals',[])]:
        # Scores and normalized momentum are not buyer counts or purchase growth.
        for evidence in signal.get('source_observations',[]):
            rows.append({**evidence,'kind':'search_interest','is_test':False})
    return rows


def upwork_observations(path):
    rows=[]
    with open(path,newline='',encoding='utf-8-sig') as file:
        for row in csv.DictReader(file):
            lowered={key.lower():value for key,value in row.items()}
            url=lowered.get('url') or lowered.get('job url')
            date=lowered.get('posted_at') or lowered.get('date')
            if not url or not date: continue
            rows.append({'kind':'buyer_request','source':'upwork', 'record_id':lowered.get('job id') or sha256(url.encode()).hexdigest(),
                'url':url,'observed_at':date,'text':(lowered.get('title','')+' '+lowered.get('description','')).strip(),'is_test':False})
    return rows


def search_observations(max_queries=8, failure_log=None, cache_dir=None):
    if type(max_queries) is not int or not 1<=max_queries<=8: raise ValueError('Search query limit must be 1–8')
    key=os.getenv('SERPAPI_API_KEY') or os.getenv('SERP_API_KEY')
    if not key: raise ValueError('Search provider credential is missing')
    rows=[]
    failures=[]
    cache=Path(cache_dir) if cache_dir else Path(__file__).resolve().parents[2]/'data/devspace_services/source_cache'
    cache.mkdir(parents=True,exist_ok=True)
    for service in list(SERVICES.values())[:max_queries]:
        query='"'+service['terms'][0]+'" ("looking for" OR "need help" OR "hiring")'
        path=cache/(sha256(query.encode()).hexdigest()+'.json')
        try:
            if path.is_file() and datetime.now(timezone.utc).timestamp()-path.stat().st_mtime<86400:
                cached=json.loads(path.read_text())
                if isinstance(cached,list): rows.extend(cached); continue
            response=requests.get('https://serpapi.com/search.json',params={'engine':'google','api_key':key,'q':query,'num':10},
                timeout=20,allow_redirects=False)
            if response.status_code!=200: raise RuntimeError('Search request rejected')
            body=response.json()
            if not isinstance(body,dict) or body.get('error'): raise RuntimeError('Invalid search response')
            found=[]
            for item in body.get('organic_results',[])[:10]:
                url=item.get('link','')
                if not url.startswith('https://'): continue
                found.append({'kind':'web_mention','source':'public_search','record_id':sha256(url.encode()).hexdigest(),
                    'url':url,'observed_at':datetime.now(timezone.utc).isoformat(),
                    'text':item.get('title','')+' '+item.get('snippet',''),'is_test':False,
                    'search_query':query,'date_scope':'Retrieval time; publication date and active request not verified'})
            rows.extend(found)
            temp=path.with_suffix('.tmp');temp.write_text(json.dumps(found));temp.replace(path)
        except (requests.RequestException,ValueError,RuntimeError):
            failures.append({'query':query,'reason':'Search provider failed; transport details withheld'})
    if failure_log is not None: failure_log.extend(failures)
    if not rows and failures: raise RuntimeError('No service search evidence was collected')
    return rows


def job_observations():
    """Remotive's attributed public feed; hiring is a proxy for service demand."""
    try:
        response=requests.get('https://remotive.com/api/remote-jobs',
            params={'category':'software-dev','limit':200},timeout=25,allow_redirects=False)
        if response.status_code!=200 or len(response.content)>5_000_000: raise RuntimeError('Job feed unavailable')
        payload=response.json()
        if not isinstance(payload.get('jobs'),list): raise RuntimeError('Invalid job feed')
    except (requests.RequestException,ValueError,RuntimeError):
        raise RuntimeError('Remotive job collection failed; transport details withheld') from None
    rows=[]
    for job in payload['jobs'][:200]:
        date=job.get('publication_date')
        if not date or not job.get('url'): continue
        # Public API timestamps lack a timezone. Retain only the source calendar
        # date instead of inventing precise publication time.
        published=datetime.fromisoformat(date.replace('Z','+00:00')).date().isoformat()+'T00:00:00+00:00'
        text=job.get('title','')+' '+html.unescape(re.sub('<[^>]+>',' ',job.get('description','')))
        rows.append({'kind':'job_posting','source':'remotive','record_id':str(job['id']),
            'url':job['url'],'observed_at':published,'text':text[:4000],'is_test':False,
            'job_type':job.get('job_type'),'date_scope':'Publication date, day precision; feed listings delayed by 24 hours',
            'source_attribution':'Remotive'})
    return rows
