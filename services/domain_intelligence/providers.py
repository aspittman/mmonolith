"""Read-only evidence collectors. Paid providers require explicit CLI selection."""
import hashlib
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
import requests


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def number(value, integer=False):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean is not evidence')
    result=float(value)
    if not math.isfinite(result) or result<0 or (integer and result!=int(result)):
        raise ValueError('Invalid provider metric')
    return int(result) if integer else result


class EvidenceCache:
    """Shared SQLite cache and serialized provider rate reservations; no credentials."""
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.path=str(path)
        with sqlite3.connect(self.path) as db:
            db.execute('create table if not exists evidence_cache(key text primary key, fetched real, payload text)')
            db.execute('create table if not exists evidence_rate(provider text primary key, next_at real)')

    def fetch(self,provider,params,loader,ttl=86400,gap=0,wait=False):
        key=hashlib.sha256(json.dumps([provider,params],sort_keys=True).encode()).hexdigest()
        while True:
            delay=0
            with sqlite3.connect(self.path,timeout=30) as db:
                db.execute('begin immediate')
                row=db.execute('select fetched,payload from evidence_cache where key=?',(key,)).fetchone()
                if row and time.time()-row[0]<ttl:
                    return json.loads(row[1])
                rate=db.execute('select next_at from evidence_rate where provider=?',(provider,)).fetchone()
                if gap and rate and rate[0]>time.time():
                    delay=max(0,rate[0]-time.time())
                    if not wait:
                        raise RuntimeError(f'{provider} rate limit: retry after {math.ceil(delay)} seconds')
                else:
                    db.execute('insert or replace into evidence_rate values(?,?)',(provider,time.time()+gap))
            if not delay: break
            time.sleep(delay + .05)
        result=loader()
        with sqlite3.connect(self.path) as db:
            db.execute('insert or replace into evidence_cache values(?,?,?)',(key,time.time(),json.dumps(result,allow_nan=False)))
        return result


class NameBioRetailProvider:
    endpoint='https://api.namebio.com/retailstats'
    def __init__(self,cache): self.cache=cache

    def fetch(self,keyword,wait=False):
        keyword=keyword.strip().lower()
        if not keyword or len(keyword)>100: raise ValueError('Keyword required, at most 100 characters')
        def load():
            response=requests.post(self.endpoint,data={'keyword':keyword},timeout=30,allow_redirects=False)
            if response.status_code!=200: raise RuntimeError('NameBio HTTP failure: '+str(response.status_code))
            body=response.json()
            if body.get('status')=='error' or str(body.get('keyword','')).lower()!=keyword:
                raise ValueError('NameBio response mismatch')
            for placement in ('exact','start','end','middle'):
                row=body['data'][placement]
                number(row['sale_count'],True)
                for key in ('price_sum','price_avg','price_max','price_stddev'): number(row[key])
            return {'source':'NameBio','source_url':'https://namebio.com/','endpoint':self.endpoint,'retrieved_at':utcnow(),
                'evidence_type':'reported_aggregate','currency':'USD','keyword':keyword,'placements':body['data'],
                'limitations':['Reported retail sales of $100 or more; not all market transactions.',
                  'Aggregates have no individual sale dates, TLD filter or unsold denominator; not a domain appraisal.']}
        return self.cache.fetch('namebio_retailstats',{'keyword':keyword},load,gap=16,wait=wait)


class KeywordDemandProvider:
    """Reuse MMonolith's existing DataForSEO transport, preserving raw keyword rows."""
    def __init__(self,cache,login,password,location_code=2840,language_code='en'):
        from services.trends.providers import DataForSEOProvider
        self.provider=DataForSEOProvider(login,password,{},location_code,language_code)
        self.cache=cache

    def fetch(self,keywords):
        params={'keywords':sorted(set(keywords)),'location_code':self.provider.location_code,'language_code':self.provider.language_code}
        if not 1<=len(params['keywords'])<=1000: raise ValueError('1–1000 keywords required')
        def load():
            rows=self.provider.fetch_keyword_data(params['keywords'])
            if not isinstance(rows,list): raise ValueError('Invalid keyword response')
            requested={k.lower() for k in keywords}
            for row in rows:
                if row['keyword'].lower() not in requested: raise ValueError('Unrequested keyword returned')
                for key in ('search_volume','cpc','competition_index'):
                    number(row.get(key),key=='search_volume')
            return {'source':'DataForSEO / Google Ads','source_url':'https://dataforseo.com/keyword-planner-api',
              'retrieved_at':utcnow(),'evidence_type':'provider_estimate','query':params,'keywords':rows,
              'limitations':['Keyword search demand and advertising prices are not domain resale demand.']}
        return self.cache.fetch('dataforseo_keywords',params,load,ttl=30*86400)


class NamecheapAvailabilityProvider:
    """Only domains.check and users.getPricing are permitted; this adapter cannot register a domain."""
    endpoint='https://api.namecheap.com/xml.response'
    def __init__(self,cache,api_user,api_key,username,client_ip):
        if not all((api_user,api_key,username,client_ip)): raise ValueError('Namecheap credentials and whitelisted client IP required')
        self.cache=cache
        self.auth={'ApiUser':api_user,'ApiKey':api_key,'UserName':username,'ClientIp':client_ip}

    def prices(self):
        import xml.etree.ElementTree as ET
        def load():
            response=requests.post(self.endpoint,data={**self.auth,'Command':'namecheap.users.getPricing',
                'ProductType':'DOMAIN','ProductCategory':'DOMAINS'},timeout=30,allow_redirects=False)
            if response.status_code!=200: raise RuntimeError('Namecheap pricing HTTP failure')
            root=ET.fromstring(response.content)
            if root.attrib.get('Status')!='OK': raise RuntimeError('Namecheap pricing failed')
            prices={}
            for category in root.iter():
                if category.tag.rsplit('}',1)[-1]!='ProductCategory' or category.attrib.get('Name') not in ('REGISTER','RENEW'): continue
                action=category.attrib['Name'].lower()
                for product in category:
                    extension=product.attrib.get('Name','').lower()
                    for price in product:
                        a=price.attrib
                        if a.get('Duration')=='1' and a.get('DurationType')=='YEAR':
                            prices.setdefault(extension,{})[action]={'price':number(a.get('Price')),'currency':a.get('Currency')}
            return prices
        return self.cache.fetch('namecheap_pricing',{'account':hashlib.sha256(self.auth['ApiUser'].encode()).hexdigest()},load)

    def fetch(self,domains):
        import xml.etree.ElementTree as ET
        domains=sorted(set(domains))
        if not 1<=len(domains)<=50: raise ValueError('Check 1–50 domains at a time')
        def load():
            response=requests.post(self.endpoint,data={**self.auth,'Command':'namecheap.domains.check','DomainList':','.join(domains)},timeout=30,allow_redirects=False)
            if response.status_code!=200: raise RuntimeError('Namecheap HTTP failure: '+str(response.status_code))
            root=ET.fromstring(response.content)
            if root.attrib.get('Status')!='OK': raise RuntimeError('Namecheap check failed')
            results={}
            prices=self.prices() if any(r.attrib.get('IsPremiumName')=='false' for r in root.iter() if r.tag.rsplit('}',1)[-1]=='DomainCheckResult') else {}
            for row in root.iter():
                if row.tag.rsplit('}',1)[-1]!='DomainCheckResult': continue
                a=row.attrib; domain=a['Domain'].lower()
                if domain not in domains or a.get('ErrorNo','0')!='0': raise ValueError('Invalid registrar response')
                premium=a.get('IsPremiumName')=='true'
                standard=prices.get(domain.rsplit('.',1)[1],{})
                registration=standard.get('register',{})
                renewal=standard.get('renew',{})
                results[domain]={'status':'available' if a.get('Available')=='true' else 'unavailable',
                  'provider':'Namecheap','checked_at':utcnow(),'source_url':'https://www.namecheap.com/',
                  'is_premium':premium,'currency':'USD' if premium else registration.get('currency'),
                  'acquisition_price':number(a.get('PremiumRegistrationPrice')) if premium else registration.get('price'),
                  'renewal_price':number(a.get('PremiumRenewalPrice')) if premium else renewal.get('price'),
                  'icann_fee':number(a.get('IcannFee')),'eap_fee':number(a.get('EapFee')),
                  'price_note':'One-year registrar quote; separately reported ICANN/EAP fees are additional. Recheck before any purchase.'}
            if set(results)!=set(domains): raise ValueError('Incomplete registrar response')
            return results
        return self.cache.fetch('namecheap_availability',{'domains':domains,'account':hashlib.sha256(self.auth['ApiUser'].encode()).hexdigest()},load,ttl=900,gap=2)
