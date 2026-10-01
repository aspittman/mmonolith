"""Register missing confirmed client service identities; preserve all existing settings."""
import json
from pathlib import Path
from dotenv import dotenv_values
from services.devspace_clients.profiles import ClientProfile
from services.shared.supabase import ClientResearchSupabase

values = dotenv_values('/home/aaron/MyBotz/devspace-crm/.env.local')
client = ClientResearchSupabase(values['NEXT_PUBLIC_SUPABASE_URL'], values['SUPABASE_SERVICE_ROLE_KEY'])
proposed = json.loads(Path('data/devspace_clients/initial_profiles.json').read_text())
registered = []
for row in proposed:
    ClientProfile.from_service(row)
    existing = client.rows('organization_services', {'select': '*', 'organization_id': 'eq.' + row['organization_id'],
        'service_key': 'eq.devspace_clients', 'niche': 'eq.client-growth'})
    if existing:
        registered.append(existing[0]); continue
    client.call('POST', 'organization_services', payload=row)
    registered.append(row)
Path('data/devspace_clients/registered_profiles.json').write_text(json.dumps(registered, indent=2)+'\n')
print(json.dumps({'registered_clients': len(registered), 'emails_enabled': False, 'existing_services_preserved': True}))
