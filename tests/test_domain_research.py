import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from services.domain_intelligence.providers import EvidenceCache, NameBioRetailProvider, KeywordDemandProvider, NamecheapAvailabilityProvider
from services.domain_intelligence.research import build_research
from devspace_domain_research.market_data import normalize_sale
from scripts.domain_research_fixture import fixture_bundle

ORG='11111111-1111-4111-8111-111111111111'

class ResearchTests(unittest.TestCase):
    def test_legacy_score_is_preserved_but_does_not_select_findings(self):
        bundle=fixture_bundle(ORG,'one',{})
        report=bundle['report']
        self.assertIsNone(report['overall_score'])
        candidate=report['metadata']['candidates'][0]
        self.assertEqual(candidate['comparable_count'],12)
        self.assertEqual(candidate['comparable_median'],1000)
        self.assertIn('legacy_comparison',candidate)
        self.assertEqual(bundle['signals'],[])
        self.assertEqual(candidate['research_owner'],'mmonolith')

    def test_no_data_never_falls_back_to_arbitrary_score(self):
        bundle=build_research(ORG,'empty','hvac',['hvac'],[],[],candidates=['hvacexample.com'],legacy=True)
        row=bundle['report']['metadata']['candidates'][0]
        self.assertIsNone(row['comparable_median'])
        self.assertEqual(row['comparable_count'],0)
        self.assertEqual(bundle['report']['confidence_score'],0)
        self.assertIn('No individual comparable sales',row['missing_evidence'])
        self.assertEqual(bundle['predictions'],[])
        no_seeds=build_research(ORG,'no-seeds','hvac',['hvac'],[],[])
        self.assertEqual(no_seeds['report']['metadata']['candidates'],[])

    def test_crm_performance_is_internal_and_does_not_change_sales_comparables(self):
        data={'rows':[{'domain':'hvacexample.com','sent':40,'positive_responses':2,
            'negative_responses':10,'sale_price':None,'gross_profit':None}]}
        bundle=build_research(ORG,'feedback','hvac',['hvac'],[],[],
            candidates=['hvacexample.com'],performance=data)
        row=bundle['report']['metadata']['candidates'][0]
        self.assertEqual(row['internal_performance']['sent'],40)
        self.assertEqual(row['internal_performance']['negative_responses'],10)
        self.assertEqual(row['comparable_count'],0)
        self.assertIsNone(row['comparable_median'])

    def test_buyer_tenant_and_subject_are_enforced(self):
        with self.assertRaises(ValueError):
            build_research(ORG,'x','hvac',['hvac'],[],[],buyers={'organization_id':'other','subject_key':'hvac'})

    def test_nonfinite_sales_prices_are_quarantined(self):
        row,flags=normalize_sale({'domain':'hvac.com','sale_price':'NaN','sale_date':'2026-01-01','currency':'USD'})
        self.assertIsNone(row)
        self.assertIn('invalid_price',flags)

    def test_namebio_raw_data_cache_rate_and_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider=NameBioRetailProvider(EvidenceCache(Path(tmp)/'cache.sqlite3'))
            body={'keyword':'hvac','data':{p:{'sale_count':5,'price_sum':5000,'price_avg':1000,'price_max':2000,'price_stddev':500} for p in ('exact','start','end','middle')}}
            with patch('services.domain_intelligence.providers.requests.post',return_value=Mock(status_code=200,json=lambda:body)) as post:
                first=provider.fetch('hvac');again=provider.fetch('hvac')
                self.assertEqual(first,again);self.assertEqual(post.call_count,1)
                self.assertEqual(first['placements']['end']['sale_count'],5)
                self.assertEqual(first['source_url'],'https://namebio.com/')
                with self.assertRaises(RuntimeError): provider.fetch('plumbing')

    def test_cache_waits_for_serialized_provider_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=EvidenceCache(Path(tmp)/'cache.sqlite3')
            self.assertEqual(cache.fetch('provider',{'term':'a'},lambda:'a',gap=.02),'a')
            self.assertEqual(cache.fetch('provider',{'term':'b'},lambda:'b',gap=.02,wait=True),'b')

    def test_failed_provider_does_not_create_successful_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider=NameBioRetailProvider(EvidenceCache(Path(tmp)/'cache.sqlite3'))
            with patch('services.domain_intelligence.providers.requests.post',return_value=Mock(status_code=403)):
                with self.assertRaises(RuntimeError): provider.fetch('hvac')
            import sqlite3
            with sqlite3.connect(Path(tmp)/'cache.sqlite3') as db:
                self.assertEqual(db.execute('select count(*) from evidence_cache').fetchone()[0],0)

    def test_keyword_metrics_remain_raw_and_missing_cpc_is_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider=KeywordDemandProvider(EvidenceCache(Path(tmp)/'cache.sqlite3'),'test','test')
            with patch.object(provider.provider,'fetch_keyword_data',return_value=[{'keyword':'hvac','search_volume':200,'cpc':None}]):
                result=provider.fetch(['hvac'])
            self.assertIsNone(result['keywords'][0]['cpc'])
            self.assertNotIn('score',result)

    def test_registrar_reads_standard_quotes_without_purchase_commands(self):
        check=b'<ApiResponse Status="OK"><DomainCheckResult Domain="hvacexample.com" Available="true" IsPremiumName="false" ErrorNo="0" IcannFee="0.18" /></ApiResponse>'
        pricing=b'<ApiResponse Status="OK"><ProductCategory Name="REGISTER"><Product Name="com"><Price Duration="1" DurationType="YEAR" Price="12" Currency="USD" /></Product></ProductCategory><ProductCategory Name="RENEW"><Product Name="com"><Price Duration="1" DurationType="YEAR" Price="16" Currency="USD" /></Product></ProductCategory></ApiResponse>'
        with tempfile.TemporaryDirectory() as tmp:
            provider=NamecheapAvailabilityProvider(EvidenceCache(Path(tmp)/'cache.sqlite3'),'user','secret','user','127.0.0.1')
            with patch('services.domain_intelligence.providers.requests.post',side_effect=[Mock(status_code=200,content=check),Mock(status_code=200,content=pricing)]) as post:
                result=provider.fetch(['hvacexample.com'])
                self.assertEqual(provider.fetch(['hvacexample.com']),result)
                self.assertEqual([c.kwargs['data']['Command'] for c in post.call_args_list],['namecheap.domains.check','namecheap.users.getPricing'])
            row=result['hvacexample.com']
            self.assertEqual((row['acquisition_price'],row['renewal_price'],row['currency']),(12,16,'USD'))
            self.assertEqual(row['icann_fee'],.18)
            self.assertNotIn('secret',(Path(tmp)/'cache.sqlite3').read_bytes().decode(errors='ignore'))

    def test_registrar_rejects_incomplete_domain_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider=NamecheapAvailabilityProvider(EvidenceCache(Path(tmp)/'cache.sqlite3'),'user','secret','user','127.0.0.1')
            with patch('services.domain_intelligence.providers.requests.post',return_value=Mock(status_code=200,content=b'<ApiResponse Status="OK"/>')):
                with self.assertRaises(ValueError): provider.fetch(['hvacexample.com'])

if __name__=='__main__':unittest.main()


def test_publish_context_is_explicit_and_does_not_mutate_bundle():
    from services.domain_intelligence.client import LoopClient
    from unittest.mock import patch
    import pytest
    org='11111111-1111-4111-8111-111111111111'
    client=LoopClient('http://localhost','fixture')
    bundle={'report':{'metadata':{}}}
    context={'workflow_run_id':'run','service_id':'domain_merchant','organization_id':org,'correlation_id':'22222222-2222-4222-8222-222222222222'}
    with patch.object(client,'request',return_value='report') as send:
        client.publish(org,bundle,workflow_context=context)
        sent=send.call_args.kwargs['bundle']
        assert sent['report']['metadata']['workflow_context']['workflow_run_id']=='run'
        assert 'workflow_context' not in bundle['report']['metadata']
        with pytest.raises(ValueError): client.publish(org,bundle,workflow_context={**context,'organization_id':'other'})
        assert send.call_count==1
