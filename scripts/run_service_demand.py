"""Weekly demand research and advisory decisions for DevSpace; never sends outreach."""
import argparse
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import subprocess
import sys
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--organization',default='2ee8ba95-35f4-4af9-b746-12071ed8815a')
    parser.add_argument('--cycle',default=datetime.now(timezone.utc).strftime('%G-W%V'))
    parser.add_argument('--decide-only',action='store_true')
    args=parser.parse_args()
    folder=ROOT/'data/devspace_services';folder.mkdir(parents=True,exist_ok=True)
    with (folder/'cycle.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 0
        if not args.decide_only:
            from services.devspace_services.__main__ import main as research
            saved=sys.argv
            try:
                sys.argv=['service-demand','--organization',args.organization,'--run-key',args.cycle,'--jobs','--search','--github-issues','--stack-overflow','--reddit','--publish']
                research()
            finally:sys.argv=saved
        one=dotenv_values(ROOT.parent/'devspace-one/.env')
        env={**os.environ,'CRM_API_URL':one['CRM_BASE_URL'],'CRM_API_SECRET':one['CRM_BOT_API_SECRET'],'DEVSPACE_ENV':'production'}
        env.pop('PYTHONPATH',None)
        return subprocess.run([sys.executable,'-m','decision_engine.main','--organization',args.organization,
            '--trigger','NEW_INTELLIGENCE_REPORT'],cwd=ROOT.parent/'decision_engine',env=env,timeout=120).returncode


if __name__=='__main__':raise SystemExit(main())
