"""Collect one bounded Utah client research sample using the existing search account."""
import argparse
import json
import os
from pathlib import Path
from dotenv import dotenv_values
from services.devspace_clients.profiles import ClientProfile
from services.devspace_clients.providers import SerpAPIProvider
from services.devspace_clients.pipeline import run_profile
from services.shared.outbox import Outbox

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--organization', default='20ea8b66-cc49-48e5-972e-2e89ed9a27e5')
parser.add_argument('--run-key', required=True)
args = parser.parse_args()
values = dotenv_values('/home/aaron/MyBotz/devspace-one/.env')
os.environ['SERP_API_KEY'] = values['SERP_API_KEY']
rows = json.loads(Path('data/devspace_clients/initial_profiles.json').read_text())
row = next(r for r in rows if r['organization_id'] == args.organization)
profile = ClientProfile.from_service(row)
result = run_profile(profile, SerpAPIProvider(), row['config_json']['client_research'], None,
    Outbox('data/devspace_clients/publications.sqlite3'), args.run_key)
root = Path('data/devspace_clients/reports')/profile.organization_id
root.mkdir(parents=True, exist_ok=True)
path = root/(profile.profile_id+'.json'); path.write_text(json.dumps(result, indent=2)+'\n')
metadata = result['report']['metadata']
print(json.dumps({'organization_id': profile.organization_id, 'report_path': str(path),
    'opportunities': len(metadata['opportunities']), 'competitors': len(metadata['competitors']),
    'reviewable': sum(o['status'] == 'REVIEW' for o in metadata['opportunities']), 'published': False}))
