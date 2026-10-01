import copy
import json
import tempfile
import unittest
from pathlib import Path
from services.devspace_clients.profiles import ClientProfile
from services.devspace_clients.providers import ExportProvider
from services.devspace_clients.pipeline import build_report, run_profile
from services.devspace_clients.modules import public_url
from services.shared.outbox import Outbox

ORG = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'

def service():
    return {'id': OTHER, 'organization_id': ORG, 'service_key': 'devspace_clients', 'is_enabled': True,
        'config_json': {'client_research': {'enabled': True, 'business_type': 'software', 'offer': 'Software for tech companies',
            'locations': ['Utah'], 'target_terms': ['technology'], 'queries': ['technology {location}'],
            'referrals': {'queries': ['consultant {location}'], 'target_terms': ['consultant']},
            'competition': {'queries': ['software {location}'], 'target_terms': ['software']}}}}

class Provider:
    name = 'fixture'
    calls = 0
    def discover(self, profile):
        self.calls += 1
        if profile.objective == 'competitors':
            return [{'company_name': 'Software technology competitor', 'website': 'https://competitor.test'}]
        return [{'company_name': 'Utah technology consultant', 'website': 'https://buyer.test',
            'location': 'Utah', 'location_evidence': 'source'},
            {'company_name': 'Software technology competitor', 'website': 'https://competitor.test'},
            {'company_name': 'Duplicate', 'website': 'https://www.buyer.test'},
            {'company_name': 'Private', 'website': 'http://127.0.0.1'}]

class ClientResearchTests(unittest.TestCase):
    def test_tracks_competitors_and_deduplication(self):
        row = service(); p = ClientProfile.from_service(row)
        b = build_report(p, Provider(), row['config_json']['client_research'], {}, 'cycle')
        candidates = b['report']['metadata']['opportunities']
        self.assertEqual({c['objective'] for c in candidates}, {'customers', 'referrals'})
        self.assertEqual(len(candidates), 2)
        self.assertEqual(len({c['id'] for c in candidates}), 2)
        self.assertTrue(all(c['domain'] == 'buyer.test' for c in candidates))
        self.assertEqual(b['predictions'], [])
        self.assertIsNone(b['report']['overall_score'])

    def test_missing_disabled_unknown_config(self):
        for mutate in (lambda r: r.update(service_key='domain_merchant'), lambda r: r.update(is_enabled=False),
                       lambda r: r['config_json']['client_research'].update(modules=['unknown']),
                       lambda r: r['config_json']['client_research'].update(max_queries=True)):
            row = service(); mutate(row)
            with self.assertRaises(ValueError): ClientProfile.from_service(row)

    def test_exact_retry_and_service_tenant_scope(self):
        row = service(); p = ClientProfile.from_service(row); provider = Provider()
        class Client:
            calls = 0
            def context(self, org): return {}
            def publish(self, org, bundle):
                self.calls += 1
                if self.calls == 1: raise RuntimeError('Ambiguous network response')
                return OTHER
        client = Client()
        with tempfile.TemporaryDirectory() as root:
            outbox = Outbox(Path(root)/'outbox.sqlite')
            with self.assertRaises(RuntimeError):
                run_profile(p, provider, row['config_json']['client_research'], client, outbox, 'cycle', publish=True)
            calls = provider.calls
            a = run_profile(p, provider, {}, client, outbox, 'cycle', publish=True)
            b = run_profile(p, provider, {}, client, outbox, 'cycle', publish=True)
            self.assertEqual(provider.calls, calls)
            self.assertEqual(client.calls, 2)
            self.assertEqual(a, b)
            self.assertIsNone(outbox.get('domain_merchant', ORG, 'devspace_clients:cycle'))
            self.assertIsNone(outbox.get('devspace_clients', OTHER, 'devspace_clients:cycle'))
            with self.assertRaises(ValueError): run_profile(p, provider, {}, client, outbox, 'cycle', is_test=True)

    def test_cross_tenant_export_context_and_test_history(self):
        row = service(); p = ClientProfile.from_service(row)
        with self.assertRaises(ValueError):
            build_report(p, Provider(), {}, {'intelligence_reports': [{'organization_id': OTHER}]}, 'cycle')
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'export.json'; path.write_text(json.dumps({'organization_id': OTHER, 'prospects': []}))
            with self.assertRaises(ValueError): ExportProvider(path).discover(p)
        context = {'intelligence_reports': [{'organization_id': ORG, 'id': OTHER, 'report_type': 'CLIENT_RESEARCH',
            'subject_key': 'client:' + p.profile_id, 'is_test': True, 'created_at': '2026-01-01'}]}
        b = build_report(p, Provider(), {}, context, 'cycle')
        self.assertIsNone(b['report']['previous_report_id'])

    def test_private_urls_rejected(self):
        for url in ('http://127.0.0.1', 'http://10.0.0.1', 'file:///etc/passwd', 'http://localhost', 'https://user:password@example.com', 'http://example.com:8080'):
            with self.assertRaises(ValueError): public_url(url)

if __name__ == '__main__': unittest.main()
