import unittest
from unittest.mock import Mock, patch
import requests
from services.shared.crm import ClientResearchCRM

ORG = '62539265-e1ae-4e14-8360-416747590585'


class ClientCRMTests(unittest.TestCase):
    def setUp(self):
        self.client = ClientResearchCRM('https://crm.example', 'private-key')

    def test_profile_read_uses_authenticated_crm_endpoint(self):
        row = {'organization_id': ORG, 'service_key': 'devspace_clients', 'is_enabled': True}
        response = Mock(status_code=200)
        response.json.return_value = {'success': True, 'services': [row]}
        with patch('services.shared.crm.requests.get', return_value=response) as get:
            self.assertEqual(self.client.enabled_profiles(ORG), [row])
        self.assertEqual(get.call_args.args[0], 'https://crm.example/api/bot/client-research')
        self.assertEqual(get.call_args.kwargs['params'], {'organization_id': ORG})
        self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_missing_endpoint_and_connection_failure_are_sanitized(self):
        with patch('services.shared.crm.requests.get', return_value=Mock(status_code=404)):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 404'):
                self.client.enabled_profiles(ORG)
        with patch('services.shared.crm.requests.get', side_effect=requests.ConnectionError('private-key')):
            with self.assertRaisesRegex(RuntimeError, '^CRM client profile connection failed$'):
                self.client.enabled_profiles(ORG)

    def test_mixed_tenant_roster_rejected(self):
        response = Mock(status_code=200)
        response.json.return_value = {'success': True, 'services': [
            {'organization_id': 'other', 'service_key': 'devspace_clients', 'is_enabled': True}]}
        with patch('services.shared.crm.requests.get', return_value=response):
            with self.assertRaises(ValueError):
                self.client.enabled_profiles(ORG)

    def test_publication_uses_crm_endpoint_and_records_returned_identity(self):
        bundle = {'report': {'report_type': 'CLIENT_RESEARCH', 'metadata': {'service_id': 'devspace_clients'}}}
        response = Mock(status_code=200)
        response.json.return_value = {'success': True, 'data': 'report-id'}
        with patch('services.shared.loop.requests.request', return_value=response) as request, patch('services.shared.loop.record') as receipt:
            self.assertEqual(self.client.publish(ORG, bundle), 'report-id')
        self.assertEqual(request.call_args.args[:2], ('POST', 'https://crm.example/api/bot/feedback-loop/intelligence'))
        self.assertEqual(request.call_args.kwargs['json'], {'organization_id': ORG, 'bundle': bundle})
        self.assertEqual(receipt.call_args.args[:6], ('mmonolith', 'devspace_clients', ORG, 'intelligence_reports', 'report-id', 'write_persisted'))
