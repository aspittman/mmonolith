"""Install weekly service-demand research without replacing other schedules."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
marker='# devspace_services weekly demand research'
existing=subprocess.run(['crontab','-l'],capture_output=True,text=True)
if existing.returncode and 'no crontab' not in existing.stderr.lower():
    raise SystemExit('Unable to read existing schedules')
lines=existing.stdout.splitlines()
entry=f'30 7 * * 2 cd {root} && {root}/.venv/bin/python scripts/run_service_demand.py >> {root}/data/devspace_services/scheduler.log 2>&1'
if marker in lines:
    index=lines.index(marker)
    if index+1>=len(lines) or lines[index+1]!=entry:
        raise SystemExit('Existing service-demand schedule differs; review before replacing')
else:
    result=subprocess.run(['crontab','-'],input='\n'.join(lines+['',marker,entry])+'\n',text=True,capture_output=True)
    if result.returncode:raise SystemExit('Unable to install demand schedule')
print('Demand research and advisory assessment scheduled Tuesday at 07:30 host time; existing schedules preserved.')
