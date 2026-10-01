"""CRM-owned contract using the existing bot credential."""
import requests
from urllib.parse import urlparse
from uuid import UUID
from services.domain_intelligence.monitoring_receipts import record, context_reads


class LoopClient:
    def __init__(self, base_url, secret):
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
        if workflow_context is not None:
            if workflow_context.get('organization_id') != org or not workflow_context.get('workflow_run_id') or not workflow_context.get('service_id'):
                raise ValueError('Invalid workflow context')
            from copy import deepcopy
            bundle = deepcopy(bundle)
            bundle['report']['metadata']['workflow_context'] = {**workflow_context, 'source_engine':'mmonolith'}
            bundle['report']['correlation_id'] = workflow_context['correlation_id']
        result = self.request('POST', 'intelligence', org, bundle=bundle)
        record('mmonolith', 'domain_merchant', org, 'intelligence_reports', result, 'write_persisted', workflow_context)
        return result

    def performance(self, org):
        """Read organization-scoped observed domain outreach and sale outcomes."""
        org = str(UUID(org))
        try:
            response = requests.get(self.url.split('/api/bot/feedback-loop/')[0] +
                '/api/bot/outreach-performance', headers=self.headers,
                params={'organization_id': org}, timeout=30, allow_redirects=False)
            if not 200 <= response.status_code < 300:
                raise RuntimeError('CRM performance HTTP failure: ' + str(response.status_code))
            body = response.json()
            if body.get('success') is not True or body.get('organization_id') != org:
                raise RuntimeError('Invalid CRM performance envelope')
            return body['performance']
        except requests.RequestException:
            raise RuntimeError('CRM performance connection failed') from None

    def evaluate(self, org, evaluation):
        result = self.request('POST', 'evaluations', org, evaluation=evaluation)
        record('mmonolith', 'domain_merchant', org, 'feedback_evaluations', result, 'write_persisted')
        return result

    def observe_review(self, org, result_id):
        result = self.request('POST', 'observe-review', org, execution_result_id=result_id)
        record('mmonolith', 'domain_merchant', org, 'feedback_evaluations', result, 'write_persisted')
        return result
