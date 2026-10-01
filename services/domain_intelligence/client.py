"""Domain-specific CRM operations; shared transport lives outside service packages."""
import requests
from uuid import UUID
from services.shared.loop import LoopClient as SharedLoopClient
from services.shared.receipts import record


class LoopClient(SharedLoopClient):
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
