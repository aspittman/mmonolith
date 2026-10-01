"""Read-only Supabase and deployed CRM readiness; no secret values in output."""
import json
from dotenv import dotenv_values
import requests

crm = dotenv_values('/home/aaron/MyBotz/devspace-crm/.env.local')
one = dotenv_values('/home/aaron/MyBotz/devspace-one/.env')
url = crm['NEXT_PUBLIC_SUPABASE_URL'].rstrip('/')+'/rest/v1/'
secret = crm['SUPABASE_SERVICE_ROLE_KEY']
headers = {'apikey': secret, 'Authorization': 'Bearer '+secret}
status = {}
for table, select in [('intelligence_reports', 'id,report_type,service_id'), ('execution_capabilities', 'service_key,adapter_ready'),
                      ('service_registry', 'service_id,enabled')]:
    try:
        response = requests.get(url+table, headers=headers, params={'select': select, 'limit': 10}, timeout=20)
        status[table] = {'http_status': response.status_code}
        if response.status_code == 200 and table != 'intelligence_reports':
            status[table]['records'] = response.json()
    except requests.RequestException:
        status[table] = {'error': 'Connection failed'}
try:
    response = requests.get(one['CRM_BASE_URL'].rstrip('/')+'/api/bot/client-research',
        headers={'Authorization': 'Bearer '+one['CRM_BOT_API_SECRET']}, timeout=20, allow_redirects=False)
    status['client_profile_endpoint'] = {'http_status': response.status_code}
except requests.RequestException:
    status['client_profile_endpoint'] = {'error': 'Connection failed'}
print(json.dumps(status))
