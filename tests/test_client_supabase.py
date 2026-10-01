import unittest
from unittest.mock import patch, Mock
import requests
from services.shared.supabase import ClientResearchSupabase, TABLES

ORG = '62539265-e1ae-4e14-8360-416747590585'


class ClientBackendTests(unittest.TestCase):
    def setUp(self):
        self.client = ClientResearchSupabase('https://example.supabase.co', 'private-key')

    def test_history_queries_are_tenant_scoped(self):
        with patch.object(self.client, 'rows', return_value=[]) as rows:
            result = self.client.request('GET', 'context', ORG)
        self.assertEqual(set(result), set(TABLES))
        for call in rows.call_args_list:
            self.assertEqual(call.args[1]['organization_id'], 'eq.' + ORG)

    def test_roster_excludes_other_services_and_disabled_profiles(self):
        with patch.object(self.client, 'rows', return_value=[]) as rows:
            self.client.enabled_profiles(ORG)
        filters = rows.call_args.args[1]
        self.assertEqual(filters['service_key'], 'eq.devspace_clients')
        self.assertEqual(filters['is_enabled'], 'eq.true')
        self.assertEqual(filters['organization_id'], 'eq.' + ORG)

    def test_no_approval_or_arbitrary_table_access(self):
        with self.assertRaises(ValueError):
            self.client.request('POST', 'approve', ORG)
        with self.assertRaises(ValueError):
            self.client.rows('profiles', {})

    def test_transport_errors_do_not_expose_credentials(self):
        with patch('services.shared.supabase.requests.request', side_effect=requests.ConnectionError('private-key')):
            with self.assertRaisesRegex(RuntimeError, '^Supabase transport failed$'):
                self.client.call('GET', 'organization_services')
        response = Mock(status_code=403)
        with patch('services.shared.supabase.requests.request', return_value=response):
            with self.assertRaisesRegex(RuntimeError, '^Supabase contract request failed: HTTP 403$'):
                self.client.call('GET', 'organization_services')
