"""Backend-only rollout transport using the same CRM-owned publication RPC.

This is for an engine host with a service-role credential, never a client session.
It provides no approval or credential-management operations.
"""
from uuid import UUID
import requests
from .loop import LoopClient

TABLES = ('intelligence_reports', 'market_signals', 'intelligence_report_signals', 'predictions',
    'feedback_evaluations', 'intelligence_report_feedback', 'execution_results', 'execution_requests', 'recommendation_evidence')


class ClientResearchSupabase(LoopClient):
    def __init__(self, url, secret, service_id='devspace_clients'):
        super().__init__(url, secret, service_id)
        self.rest = url.rstrip('/') + '/rest/v1/'
        self.headers = {'apikey': secret, 'Authorization': 'Bearer ' + secret}

    def call(self, method, path, *, params=None, payload=None):
        try:
            response = requests.request(method, self.rest + path, headers=self.headers,
                params=params, json=payload, timeout=30, allow_redirects=False)
            if not 200 <= response.status_code < 300:
                raise RuntimeError('Supabase contract request failed: HTTP ' + str(response.status_code))
            return response.json() if response.content else None
        except (requests.RequestException, ValueError):
            raise RuntimeError('Supabase transport failed') from None

    def rows(self, table, params):
        if table not in (*TABLES, 'organization_services'):
            raise ValueError('Unsupported client research table')
        rows = []
        while True:
            page = self.call('GET', table, params={**params, 'order': 'id', 'offset': len(rows), 'limit': 500})
            if not isinstance(page, list): raise RuntimeError('Invalid Supabase row envelope')
            rows.extend(page)
            if len(page) < 500: return rows

    def request(self, method, route, org, **payload):
        org = str(UUID(org))
        if method == 'GET' and route == 'context':
            return {table: self.rows(table, {'organization_id': 'eq.' + org, 'select': '*'}) for table in TABLES}
        if method == 'POST' and route == 'intelligence' and set(payload) == {'bundle'}:
            return self.call('POST', 'rpc/loop_publish', payload={'p_org': org, 'p_bundle': payload['bundle']})
        raise ValueError('Unsupported backend research operation')

    def enabled_profiles(self, organization_id=None):
        filters = {'select': 'id,organization_id,service_key,niche,is_enabled,config_json',
            'service_key': 'eq.' + self.service_id, 'is_enabled': 'eq.true'}
        if organization_id: filters['organization_id'] = 'eq.' + str(UUID(organization_id))
        return self.rows('organization_services', filters)
