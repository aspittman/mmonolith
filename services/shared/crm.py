"""Reusable CRM transport, retaining the established domain compatibility API."""
from uuid import UUID
import requests
from services.shared.loop import LoopClient


class ClientResearchCRM(LoopClient):
    def __init__(self, base_url, secret):
        super().__init__(base_url, secret, service_id='devspace_clients')

    def enabled_profiles(self, organization_id=None):
        params = {}
        if organization_id:
            params['organization_id'] = str(UUID(organization_id))
        response = requests.get(self.url.split('/api/bot/feedback-loop/')[0] +
            '/api/bot/client-research', headers=self.headers, params=params, timeout=30, allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError('CRM client profile request failed')
        body = response.json()
        if body.get('success') is not True or not isinstance(body.get('services'), list):
            raise RuntimeError('Invalid client profile envelope')
        rows = body['services']
        if any(r.get('service_key') != self.service_id or r.get('is_enabled') is not True or
               (organization_id and r.get('organization_id') != organization_id) for r in rows):
            raise ValueError('Client profile scope mismatch')
        return rows
