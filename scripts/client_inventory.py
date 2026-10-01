"""Read-only client readiness inventory; never prints credentials or contacts."""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv('/home/aaron/MyBotz/devspace-crm/.env.local')
base = os.environ['NEXT_PUBLIC_SUPABASE_URL'].rstrip('/') + '/rest/v1/'
secret = os.environ['SUPABASE_SERVICE_ROLE_KEY']
headers = {'apikey': secret, 'Authorization': 'Bearer ' + secret}
def rows(table, select):
    response = requests.get(base + table, headers=headers, params={'select': select}, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f'{table}: HTTP {response.status_code}')
    return response.json()
organizations = rows('organizations', 'id,name,type')
services = rows('organization_services', 'organization_id,service_key,niche,is_enabled,email_enabled,config_json')
for org in organizations:
    configs = [s for s in services if s['organization_id'] == org['id']]
    print(json.dumps({'organization_id': org['id'], 'name': org['name'], 'type': org['type'],
        'services': [{'service_key': s['service_key'], 'niche': s['niche'], 'enabled': s['is_enabled'],
            'email_enabled': s['email_enabled'], 'config_keys': sorted((s['config_json'] or {}).keys())} for s in configs]}))
