import unittest
import tempfile
from unittest.mock import patch, Mock
from datetime import datetime, timezone, timedelta
from services.devspace_services.evidence import collect
from services.devspace_services.pipeline import build_bundle
from services.devspace_services.sources import google_play_observations, search_observations
from services.shared.supabase import ClientResearchSupabase
from services.devspace_services.google_play.models import AppRecord

NOW=datetime(2026,10,1,tzinfo=timezone.utc)
ORG='2ee8ba95-35f4-4af9-b746-12071ed8815a'


def observation(**kwargs):
    return {'kind':'buyer_request','source':'authorized_marketplace','record_id':'1',
        'url':'https://example.org/jobs/1','observed_at':NOW.isoformat(),
        'text':'Need an API integration with reporting dashboard','is_test':False,**kwargs}


class ServiceDemandTests(unittest.TestCase):
    def test_pricing_does_not_block_research_and_products_stay_distinct(self):
        report=build_bundle(ORG,[observation()],{}, {},'one',now=NOW)['report']
        self.assertEqual(report['report_type'],'SERVICE_DEMAND')
        self.assertIsNone(report['overall_score'])
        self.assertEqual({o['id'] for o in report['metadata']['opportunities']},{'api_integrations','analytics_setup'})
        for o in report['metadata']['opportunities']:
            self.assertEqual(o['opportunity_type'],'SERVICE')
            self.assertEqual(o['recommendation'],'RESEARCH_SERVICE')
            self.assertIsNone(o['estimated_price'])
            self.assertEqual(o['explicit_requests'],1)
        self.assertEqual(AppRecord.__module__, "services.devspace_services.google_play.models")

    def test_duplicates_stale_future_and_fake_data(self):
        rows=[observation(),observation(record_id='2'),observation(record_id='3',url='https://example.org/old',
            observed_at=(NOW-timedelta(days=31)).isoformat()), observation(record_id='4',url='https://example.org/future',
            observed_at=(NOW+timedelta(days=1)).isoformat())]
        self.assertEqual(len(collect(rows,NOW)),1)
        with self.assertRaises(ValueError):collect([observation(is_test=True)],NOW)
        with self.assertRaises(ValueError):google_play_observations({'demo_data':True,'niches':[]})

    def test_search_mentions_are_not_verified_requests_or_high_confidence(self):
        report=build_bundle(ORG,[observation(kind='web_mention')],{}, {},'one',now=NOW)['report']
        self.assertEqual(report['confidence_score'],.15)
        for o in report['metadata']['opportunities']:
            self.assertEqual(o['explicit_requests'],0)
            self.assertIsNone(o['observed_request_share_percent'])

    def test_growth_requires_comparable_real_measurements(self):
        comparison={'previous':100,'current':131,'unit':'request_count','window_days':7,
            'previous_end':(NOW-timedelta(days=7)).isoformat(),'current_end':NOW.isoformat()}
        result=collect([observation(comparison=comparison)],NOW)[0]
        self.assertEqual(result['comparison']['change_percent'],31)
        comparison['previous']=0
        self.assertIsNone(collect([observation(comparison=comparison)],NOW)[0]['comparison']['change_percent'])
        comparison['current']=float('nan')
        with self.assertRaises(ValueError):collect([observation(comparison=comparison)],NOW)

    def test_publication_scope_and_cross_tenant_outcomes(self):
        client=ClientResearchSupabase('https://example.supabase.co','key','devspace_services')
        with self.assertRaises(ValueError):client.publish(ORG,{'report':{'report_type':'CLIENT_RESEARCH'}})
        with self.assertRaises(ValueError):build_bundle(ORG,[observation()],{},
            {'execution_results':[{'organization_id':'other'}]},'one',now=NOW)

    def test_partial_search_is_preserved_and_successful_queries_are_cached(self):
        good=Mock(status_code=200)
        good.json.return_value={'organic_results':[{'title':'API integration help','link':'https://example.org/real-source','snippet':'Looking for integration help'}]}
        failed=Mock(status_code=403)
        with tempfile.TemporaryDirectory() as cache, patch.dict('os.environ',{'SERPAPI_API_KEY':'private-key'}):
            failures=[]
            with patch('services.devspace_services.sources.requests.get',side_effect=[good,failed]) as request:
                rows=search_observations(2,failures,cache)
            self.assertEqual(len(rows),1)
            self.assertEqual(len(failures),1)
            self.assertEqual(rows[0]['kind'],'web_mention')
            self.assertEqual(request.call_count,2)
            with patch('services.devspace_services.sources.requests.get',return_value=failed) as request:
                again=search_observations(2,[],cache)
            self.assertEqual(again,rows)
            self.assertEqual(request.call_count,1)

class CorroborationTests(unittest.TestCase):
    def test_many_requests_on_one_platform_do_not_outweigh_independent_sources(self):
        from services.devspace_services.corroboration import research_score, corroboration
        many=[observation(source='upwork_alias_'+str(i),record_id=str(i),url='https://www.upwork.com/jobs/'+str(i)) for i in range(100)]
        mixed=[many[0],observation(kind='technical_pain',source='reddit',record_id='r',url='https://www.reddit.com/r/business/comments/1',text='Need API integration help'),
            observation(kind='technical_pain',source='github_issues',record_id='g',url='https://github.com/org/repo/issues/1',text='API integration fails'),
            observation(kind='search_interest',source='google_trends',record_id='t',url='https://trends.google.com/trends/explore?q=api',text='API integration')]
        self.assertEqual(corroboration(many)['independent_source_count'],1)
        self.assertGreater(research_score(mixed),research_score(many))
        self.assertEqual(corroboration(mixed)['status'],'CROSS_SOURCE_DEMAND')

    def test_supply_snippets_and_syndication_do_not_manufacture_confirmation(self):
        from services.devspace_services.corroboration import corroboration
        rows=[observation(url='https://upwork.com/jobs/1'),observation(kind='web_mention',url='https://reddit.com/r/business/1'),
            observation(kind='competitor_offer',url='https://fiverr.com/seller/api')]
        self.assertEqual(corroboration(rows)['independent_source_count'],1)
        long='API integration needed for our customer reporting dashboard and data pipeline. '*3
        rows=[observation(text=long,url='https://upwork.com/jobs/1'),observation(text=long,url='https://example.com/jobs/2')]
        self.assertEqual(corroboration(rows)['independent_source_count'],1)

    def test_declining_interest_is_visible_but_does_not_confirm_demand(self):
        from services.devspace_services.corroboration import corroboration
        trend=observation(kind='search_interest',url='https://trends.google.com/trends/explore',id='declining',comparison={'previous':100,'current':60})
        result=corroboration([trend])
        self.assertEqual(result['independent_source_count'],0)
        self.assertEqual(result['declining_interest_evidence_ids'],['declining'])

    def test_authorized_export_enforces_platform_and_live_organization(self):
        import json
        from pathlib import Path
        from services.devspace_services.research_sources import export_observations
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fiverr.json'
            payload={'organization_id':ORG,'demo_data':False,'observations':[observation(kind='competitor_offer',url='https://fiverr.com/seller/api')]}
            path.write_text(json.dumps(payload))
            self.assertEqual(export_observations(path,'fiverr',ORG)[0]['source'],'fiverr')
            payload['observations'][0]['kind']='buyer_request';path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError): export_observations(path,'fiverr',ORG)

    def test_public_technical_apis_keep_pain_separate_and_honor_backoff(self):
        from services.devspace_services.research_sources import technical_observations
        response=Mock(status_code=200,content=b'{}')
        response.json.return_value={'items':[{'question_id':1,'link':'https://stackoverflow.com/questions/1',
            'creation_date':int(NOW.timestamp()),'title':'API integration','body':'Need help'}],'backoff':10}
        with patch('services.devspace_services.research_sources.requests.get',return_value=response) as request:
            rows=technical_observations('stack_overflow',2)
        self.assertEqual(request.call_count,1)
        self.assertEqual(rows[0]['kind'],'technical_pain')
