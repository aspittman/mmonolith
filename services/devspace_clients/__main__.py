"""Run isolated customer/referral/competition research for one or all configured clients."""
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from .profiles import ClientProfile
from .providers import ExportProvider, SerpAPIProvider
from .pipeline import run_profile
from services.shared.crm import ClientResearchCRM
from services.shared.outbox import Outbox


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--organization')
    parser.add_argument('--profiles', help='Local JSON array of organization service rows')
    parser.add_argument('--export', help='Tenant-scoped authorized prospect export (one organization only)')
    parser.add_argument('--provider', choices=['serpapi'])
    parser.add_argument('--run-key', required=True, help='Stable cycle key; retries reuse the exact saved report')
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--outbox', default='data/devspace_clients/publications.sqlite3')
    parser.add_argument('--output', default='data/devspace_clients/reports')
    args = parser.parse_args()
    if bool(args.export) == bool(args.provider):
        parser.error('Choose exactly one of --export or --provider')
    if args.test and os.getenv('DEVSPACE_ENV') != 'test':
        parser.error('--test requires DEVSPACE_ENV=test')
    if args.export and not args.organization:
        parser.error('--export requires --organization')
    client = ClientResearchCRM(os.environ['CRM_BASE_URL'], os.environ['BOT_API_SECRET']) if args.publish or not args.profiles else None
    rows = json.loads(Path(args.profiles).read_text()) if args.profiles else client.enabled_profiles(args.organization)
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        parser.error('Profiles must be an array of organization service rows')
    if args.organization:
        rows = [r for r in rows if r['organization_id'] == args.organization]
    provider = ExportProvider(args.export) if args.export else SerpAPIProvider()
    outbox = Outbox(args.outbox)
    summaries, failed = [], False
    for row in rows:
        try:
            profile = ClientProfile.from_service(row)
            # Profile ID prevents collision when an organization has multiple service niches.
            key = args.run_key + ':' + profile.profile_id
            result = run_profile(profile, provider, row['config_json']['client_research'], client, outbox, key,
                publish=args.publish, is_test=args.test)
            root = Path(args.output)/profile.organization_id
            root.mkdir(parents=True, exist_ok=True)
            path = root/(profile.profile_id + '.json')
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(result, indent=2, allow_nan=False)); temporary.replace(path)
            summaries.append({'organization_id': profile.organization_id, 'status': 'PUBLISHED' if args.publish else 'RESEARCHED',
                'report_path': str(path), 'intelligence_report_id': result['intelligence_report_id']})
        except (ValueError, KeyError, RuntimeError) as error:
            failed = True
            summaries.append({'organization_id': row.get('organization_id'), 'status': 'FAILED', 'error_type': type(error).__name__})
        except Exception as error:
            failed = True
            summaries.append({'organization_id': row.get('organization_id'), 'status': 'FAILED', 'error_type': type(error).__name__})
    print(json.dumps({'service_id': 'devspace_clients', 'clients': summaries, 'configured_clients': len(rows)}))
    return 1 if failed or not rows else 0


if __name__ == '__main__':
    raise SystemExit(main())
