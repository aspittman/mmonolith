"""Bounded public API collectors and explicitly live, dated authorized exports."""
from datetime import datetime, timezone, timedelta
import html
import json
import os
import re
import requests
import xml.etree.ElementTree as ET
from .catalog import SERVICES
from .corroboration import source_family

EXPORT_KINDS={'upwork':{'buyer_request'},'reddit':{'technical_pain','buyer_request'},
    'fiverr':{'competitor_offer'},'github_issues':{'technical_pain'},
    'stack_overflow':{'technical_pain'},'job_boards':{'buyer_request','job_posting'}}
SOURCE_SET=('upwork','reddit','google_trends','google_play','fiverr','github_issues','stack_overflow','job_boards','public_search')


def export_observations(path, source, organization):
    payload=json.loads(path.read_text())
    if payload.get('organization_id')!=organization or payload.get('demo_data') is not False:
        raise ValueError('Organization-scoped live export required')
    rows=payload.get('observations')
    if not isinstance(rows,list) or len(rows)>1000: raise ValueError('Invalid export size')
    result=[]
    for row in rows:
        if row.get('kind') not in EXPORT_KINDS[source] or row.get('is_test') is not False:
            raise ValueError('Export evidence kind or live declaration mismatch')
        if source!='job_boards' and source_family(row)!=source:
            raise ValueError('Source URL does not match export platform')
        result.append({**row,'source':source if source!='job_boards' else source_family(row)})
    return result


def fetch(url,params=None,headers=None):
    try:
        response=requests.get(url,params=params,headers=headers,timeout=25,allow_redirects=False)
        if response.status_code!=200 or len(response.content)>5_000_000:
            raise RuntimeError('Source rejected or exceeded collection limit')
        return response
    except requests.RequestException:
        raise RuntimeError('Source transport failed; credentials and transport details withheld') from None


def technical_observations(source, max_queries=2):
    if type(max_queries) is not int or not 1<=max_queries<=8: raise ValueError('Query limit must be 1–8')
    now=datetime.now(timezone.utc); start=now-timedelta(days=30)
    rows=[]
    for service in list(SERVICES.values())[:max_queries]:
        term=service['terms'][0]
        if source=='github_issues':
            headers={'Accept':'application/vnd.github+json','User-Agent':'DevSpace-demand-research'}
            token=os.getenv('DEVSPACE_GITHUB_TOKEN')
            if token: headers['Authorization']='Bearer '+token
            body=fetch('https://api.github.com/search/issues',{'q':f'is:issue is:open created:>={start.date()} "{term}"','per_page':20},headers).json()
            if body.get('incomplete_results'): raise RuntimeError('GitHub returned incomplete results')
            items=body.get('items')
            if not isinstance(items,list): raise RuntimeError('Invalid GitHub response')
            for item in items:
                if item.get('pull_request'): continue
                rows.append({'source':source,'kind':'technical_pain','record_id':str(item['id']),
                    'url':item['html_url'],'observed_at':item['created_at'],
                    'text':item['title']+' '+(item.get('body') or ''),'is_test':False})
        elif source=='stack_overflow':
            body=fetch('https://api.stackexchange.com/2.3/search/advanced',{'site':'stackoverflow','q':term,
                'fromdate':int(start.timestamp()),'todate':int(now.timestamp()),'pagesize':20,'filter':'withbody','sort':'creation','order':'desc'}).json()
            items=body.get('items')
            if not isinstance(items,list): raise RuntimeError('Invalid Stack Overflow response')
            for item in items:
                rows.append({'source':source,'kind':'technical_pain','record_id':str(item['question_id']),
                    'url':item['link'],'observed_at':datetime.fromtimestamp(item['creation_date'],timezone.utc).isoformat(),
                    'text':html.unescape(re.sub('<[^>]+>',' ',item['title']+' '+item.get('body',''))),'is_test':False})
            # Stop requests when the provider asks for backoff; never evade rate limits.
            if body.get('backoff') or body.get('quota_remaining',1)<=0: break
        else: raise ValueError('Unknown technical API source')
    return rows


def reddit_observations(max_queries=2):
    rows=[]; ns={'a':'http://www.w3.org/2005/Atom'}
    if type(max_queries) is not int or not 1<=max_queries<=8: raise ValueError('Query limit must be 1–8')
    for service in list(SERVICES.values())[:max_queries]:
        response=fetch('https://www.reddit.com/search.rss',{'q':service['terms'][0],'sort':'new','t':'month','limit':20},
            {'User-Agent':'DevSpaceDemandResearch/1.0'})
        try: entries=ET.fromstring(response.content).findall('a:entry',ns)
        except ET.ParseError: raise RuntimeError('Invalid Reddit RSS response') from None
        for item in entries[:20]:
            link=item.find('a:link',ns); date=item.findtext('a:published',None,ns) or item.findtext('a:updated',None,ns)
            if link is None or not date: continue
            rows.append({'source':'reddit','kind':'technical_pain','record_id':item.findtext('a:id','',ns),
                'url':link.get('href'),'observed_at':date,'is_test':False,
                'text':html.unescape(re.sub('<[^>]+>',' ',item.findtext('a:title','',ns)+' '+item.findtext('a:content','',ns)))})
    return rows
