"""Install the independent weekly research schedule, preserving existing jobs."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
marker = '# devspace_clients weekly research'
current = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
if current.returncode and 'no crontab' not in current.stderr.lower():
    raise SystemExit('Unable to read existing scheduler')
lines = current.stdout.splitlines()
entry = f'30 6 * * 1 cd {root} && {root}/.venv/bin/python scripts/run_client_cycle.py --research >> {root}/data/devspace_clients/scheduler.log 2>&1'
if marker in lines:
    index = lines.index(marker)
    if index + 1 >= len(lines) or lines[index + 1] != entry:
        raise SystemExit('Existing client schedule differs; review before replacing')
else:
    content = '\n'.join(lines + ['', marker, entry]) + '\n'
    installed = subprocess.run(['crontab', '-'], input=content, text=True, capture_output=True)
    if installed.returncode:
        raise SystemExit('Unable to install client scheduler')
print('Client research scheduled weekly on Monday at 06:30 host time; existing jobs preserved.')
