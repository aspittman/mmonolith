from datetime import datetime,timezone,timedelta
import unittest
from services.shared.product_research import build_bundle, public_url
from services.shared.loop import LoopClient

NOW=datetime(2026,10,2,tzinfo=timezone.utc)
ORG='2ee8ba95-35f4-4af9-b746-12071ed8815a'
PAGE='Applicants must have GPA 3.4 or above. Applications are open. Deadline 2026-11-01. All eligibility requirements are listed here. Award amount USD 1000.'


def claim(value,quote):return {'value':value,'quote':quote}
def candidate(**changes):
    return {'name':'Official award','program_id':'award-2026','url':'https://issuer.example/award','is_test':False,
        'normalization_reviewed':True,
        'facts':{'deadline':claim('2026-11-01T00:00:00Z','Deadline 2026-11-01'),
            'award_min':claim(1000,'Award amount USD 1000'),
            'requirements_complete':claim(True,'All eligibility requirements are listed here'),
            'accepting_applications':claim(True,'Applications are open')},
        'criteria':[{'field':'gpa','operator':'gte','value':3.4,'quote':'Applicants must have GPA 3.4 or above'}],**changes}


class ProductResearchTests(unittest.TestCase):
    def bundle(self,rows,service='scholarship_research',domains=('issuer.example',),reader=lambda *_:PAGE):
        return build_bundle(service,ORG,rows,domains,'cycle',now=NOW,reader=reader)['report']

    def test_research_contains_no_user_eligibility_and_deduplicates(self):
        report=self.bundle([candidate(),candidate()]);records=report['metadata']['opportunities']
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['source_status'],'ISSUER_PAGE_VERIFIED')
        self.assertEqual(records[0]['facts']['award_min']['value'],1000)
        self.assertFalse(report['metadata']['profile_matching_performed'])
        self.assertNotIn('match_score',records[0])
        self.assertEqual(report['metadata']['coverage'],'global')

    def test_discovery_or_fetch_failure_never_verifies_facts(self):
        row=self.bundle([candidate()],domains=())['metadata']['opportunities'][0]
        self.assertEqual(row['facts'],{})
        self.assertEqual(row['source_status'],'UNVERIFIED')
        def failed(*_):raise RuntimeError('unavailable')
        report=self.bundle([candidate()],reader=failed)
        self.assertEqual(report['metadata']['collection_status'],'PARTIAL')
        self.assertEqual(report['metadata']['opportunities'][0]['criteria'],[])

    def test_unsupported_quotes_fake_and_foreign_types_are_rejected(self):
        row=candidate();row['facts']['award_min']['quote']='Made up source statement'
        with self.assertRaises(ValueError):self.bundle([row])
        with self.assertRaises(ValueError):self.bundle([candidate(is_test=True)])
        with self.assertRaises(ValueError):self.bundle([candidate(opportunity_type='VC_FIRM')])

    def test_expired_and_conflicting_records_are_retained_for_explanation(self):
        expired=candidate();expired['facts']['deadline']=claim('2026-01-01T00:00:00Z','Deadline 2026-01-01')
        report=self.bundle([expired],reader=lambda *_:PAGE.replace('2026-11-01','2026-01-01'))
        self.assertEqual(report['metadata']['opportunities'][0]['status'],'EXPIRED')
        other=candidate();other['facts'].pop('award_min')
        report=self.bundle([candidate(),other])
        self.assertEqual(report['metadata']['opportunities'][0]['status'],'SOURCE_CONFLICT')

    def test_investor_research_preserves_preferences_without_matching_company(self):
        row={'name':'Example venture fund','program_id':'seed','url':'https://issuer.example/thesis','is_test':False,
            'opportunity_type':'VC_FIRM','facts':{},'criteria':[{'field':'stage','operator':'in','value':['Seed'],
            'quote':'We invest in Seed stage businesses'}]}
        report=self.bundle([row],service='investor_research',reader=lambda *_:'We invest in Seed stage businesses')
        self.assertEqual(report['report_type'],'INVESTOR_RESEARCH')
        self.assertFalse(report['metadata']['profile_matching_performed'])

    def test_transport_identity_and_public_url_boundaries(self):
        client=LoopClient('https://example.supabase.co','key','scholarship_research')
        with self.assertRaises(ValueError):client.publish(ORG,{'report':{'report_type':'INVESTOR_RESEARCH'}})
        other=LoopClient('https://example.supabase.co','key','domain_merchant')
        with self.assertRaises(ValueError):other.publish(ORG,{'report':{'report_type':'SCHOLARSHIP_RESEARCH'}})
        for url in ['http://issuer.example/award','https://127.0.0.1/a','https://user:pass@issuer.example/a','https://localhost/a']:
            with self.assertRaises(ValueError):public_url(url)
