"""Research, publish and recommend for configured clients; never approves outreach."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from services.devspace_clients.profiles import ClientProfile
from services.devspace_clients.providers import SerpAPIProvider
from services.devspace_clients.pipeline import run_profile
from services.shared.outbox import Outbox
from services.shared.supabase import ClientResearchSupabase



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--organization')
    parser.add_argument('--cycle', default=datetime.now(timezone.utc).strftime('%G-W%V'))
    parser.add_argument('--research', action='store_true')
    parser.add_argument('--decide', action='store_true')
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if not any((args.research, args.decide, args.prepare)):
        parser.error('Choose --research, --decide and/or --prepare')
    one = dotenv_values(ROOT.parent/'devspace-one/.env')
    crm = dotenv_values(ROOT.parent/'devspace-crm/.env.local')
    os.environ['SERP_API_KEY'] = one['SERP_API_KEY']
    client = ClientResearchSupabase(crm['NEXT_PUBLIC_SUPABASE_URL'], crm['SUPABASE_SERVICE_ROLE_KEY'])
    root = ROOT/'data/devspace_clients'; root.mkdir(parents=True, exist_ok=True)
    summaries = []
    with (root/'cycle.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'service_id': 'devspace_clients', 'status': 'BUSY'})); return 0
        outbox = Outbox(root/'publications.sqlite3')
        try:
            roster = client.enabled_profiles(args.organization)
        except RuntimeError as error:
            print(json.dumps({'service_id': 'devspace_clients', 'stage': 'supabase_profile_read',
                'status': 'FAILED', 'reason': str(error)}))
            return 1
        if not roster:
            print(json.dumps({'service_id': 'devspace_clients', 'status': 'NO_CONFIGURED_CLIENTS'}))
            return 0
        for row in roster:
            org = row['organization_id']
            try:
                profile = ClientProfile.from_service(row)
                if args.research:
                    result = run_profile(profile, SerpAPIProvider(), row['config_json']['client_research'], client, outbox,
                        args.cycle + ':' + profile.profile_id, publish=True)
                    path = root/'reports'/org/(profile.profile_id + '.json'); path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix('.tmp'); temporary.write_text(json.dumps(result, indent=2)); temporary.replace(path)
                    summaries.append({'organization_id': org, 'stage': 'research', 'intelligence_report_id': result['intelligence_report_id'], 'status': 'COMPLETED'})
                env = {**os.environ, 'CRM_API_URL': one['CRM_BASE_URL'], 'CRM_API_SECRET': one['CRM_BOT_API_SECRET'],
                    'CRM_BASE_URL': one['CRM_BASE_URL'], 'CRM_BOT_API_SECRET': one['CRM_BOT_API_SECRET'], 'DEVSPACE_ENV': 'production'}
                env.pop('PYTHONPATH', None)
                if args.decide:
                    completed = subprocess.run([sys.executable, '-m', 'decision_engine.main', '--organization', org,
                        '--trigger', 'NEW_INTELLIGENCE_REPORT'], cwd=ROOT.parent/'decision_engine', env=env, timeout=120)
                    if completed.returncode: raise RuntimeError('Client decision failed')
                if args.prepare:
                    completed = subprocess.run([sys.executable, '-m', 'services.devspace_clients.worker', '--organization', org],
                        cwd=ROOT.parent/'devspace-one', env=env, timeout=120)
                    if completed.returncode: raise RuntimeError('Client preparation failed')
            except Exception as error:
                summaries.append({'organization_id': org, 'status': 'FAILED', 'error_type': type(error).__name__})
    print(json.dumps({'service_id': 'devspace_clients', 'cycle': args.cycle, 'clients': summaries}))
    return 1 if any(r['status'] == 'FAILED' for r in summaries) else 0


if __name__ == '__main__':
    raise SystemExit(main())
