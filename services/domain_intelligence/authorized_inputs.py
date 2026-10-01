"""Bounded, explicitly attributed research exports. No provider calls or spending."""
import json
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
from .service import timestamp, numeric


def envelope(path, org, subject, at=None):
    p=Path(path)
    if p.stat().st_size>2_000_000: raise ValueError('Evidence export too large')
    data=json.loads(p.read_text())
    at=at or datetime.now(timezone.utc)
    if data.get('organization_id')!=org or data.get('subject_key')!=subject:
        raise ValueError('Evidence export scope mismatch')
    if urlparse(data.get('source_url','')).scheme!='https' or timestamp(data['retrieved_at'])>at:
        raise ValueError('Evidence provenance required')
    return data


def quotes(path, org, subject, domains, at=None):
    data=envelope(path,org,subject,at)
    if data.get('contract')!='registrar-checkout-quotes-v1' or len(data.get('quotes',[]))>50:
        raise ValueError('Bounded checkout-quote contract required')
    output={}
    for row in data['quotes']:
        domain=row['domain'].lower()
        if domain not in domains: continue
        if domain in output: raise ValueError('Duplicate quote')
        if row.get('provider')!='GoDaddy' or row.get('price_type')!='checkout_total' or row.get('currency')!='USD':
            raise ValueError('GoDaddy USD checkout total required')
        if row.get('status') not in ('available','unavailable'): raise ValueError('Explicit availability required')
        checked=timestamp(row['checked_at'])
        if checked>timestamp(data['retrieved_at']): raise ValueError('Quote timestamp inconsistent')
        price=numeric(row['acquisition_price'],0)
        output[domain]={**row,'acquisition_price':price,'source_url':data['source_url'],
                        'retrieved_at':data['retrieved_at'],'ingestion':'authorized_export'}
    return output


def assessments(path, org, subject):
    data=envelope(path,org,subject)
    rows=data.get('candidates',[])
    if len(rows)>50: raise ValueError('At most 50 candidate assessments')
    output={}
    for row in rows:
        if row['domain'] in output: raise ValueError('Duplicate assessment')
        metrics=row.get('decision_metrics',{})
        for value in metrics.values():
            numeric(value['value'],0,100)
            if not value.get('source_reference') or timestamp(value['observed_at'])>timestamp(data['retrieved_at']):
                raise ValueError('Assessment provenance required')
        output[row['domain']]={'decision_metrics':metrics,'trademark_screening':row.get('trademark_screening',{})}
    return output
