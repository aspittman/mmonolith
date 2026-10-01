"""CRM-owned contract using the existing bot credential."""
import requests
from urllib.parse import urlparse
from uuid import UUID
from services.shared.receipts import record, context_reads


class LoopClient:
    def __init__(self, base_url, secret, service_id='domain_merchant'):
        if service_id not in ('domain_merchant', 'devspace_clients'):
            raise ValueError('Unsupported intelligence service')
        self.service_id = service_id
        parsed = urlparse(base_url)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
            raise ValueError('HTTPS CRM origin required (HTTP loopback allowed)')
        if not secret or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('CRM origin and bot secret required')
        self.url = base_url.rstrip('/') + '/api/bot/feedback-loop/'
        self.headers = {'Authorization': 'Bearer ' + secret}

    def request(self, method, route, org, **payload):
        org = str(UUID(org))
        kwargs = {'params': {'organization_id': org}} if method == 'GET' else {'json': {'organization_id': org, **payload}}
        try:
            response = requests.request(method, self.url + route, headers=self.headers, timeout=30, allow_redirects=False, **kwargs)
            if not 200 <= response.status_code < 300:
                raise RuntimeError('CRM HTTP failure: ' + str(response.status_code))
            body = response.json()
            if body.get('success') is not True or 'data' not in body:
                raise RuntimeError('Invalid CRM envelope')
            return body['data']
        except requests.RequestException:
            raise RuntimeError('CRM connection failed') from None

    def context(self, org):
        data = self.request('GET', 'context', org)
        if any(row.get('organization_id') != org for rows in data.values() for row in rows):
            raise ValueError('Mixed tenant context rejected')
        context_reads('mmonolith', org, data)
        return data

    def publish(self, org, bundle, *, workflow_context=None):
        report = bundle.get('report', {})
        if self.service_id == 'devspace_clients' and (report.get('report_type') != 'CLIENT_RESEARCH' or report.get('metadata', {}).get('service_id') != self.service_id):
            raise ValueError('Client research publication scope mismatch')
        if self.service_id != 'devspace_clients' and report.get('report_type') == 'CLIENT_RESEARCH':
            raise ValueError('Client research requires its own transport identity')
        if workflow_context is not None:
            if workflow_context.get('organization_id') != org or not workflow_context.get('workflow_run_id') or workflow_context.get('service_id') != self.service_id:
                raise ValueError('Invalid workflow context')
            from copy import deepcopy
            bundle = deepcopy(bundle)
            bundle['report']['metadata']['workflow_context'] = {**workflow_context, 'source_engine':'mmonolith'}
            bundle['report']['correlation_id'] = workflow_context['correlation_id']
        result = self.request('POST', 'intelligence', org, bundle=bundle)
        record('mmonolith', self.service_id, org, 'intelligence_reports', result, 'write_persisted', workflow_context)
        return result
