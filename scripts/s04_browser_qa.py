"""Owned Docker browser QA with synthetic tmpfs SQLite and no working mounts."""
from pathlib import Path
import os
import subprocess
import time
from uuid import uuid4


def main():
    backend = Path(__file__).resolve().parents[1]
    frontend = backend.parent / 'legacy-typo-frontend'
    if not frontend.is_dir():
        frontend = backend.parent / 'frontend'
    name = 's04-browser-' + uuid4().hex[:12]
    containers = [name + '-backend', name + '-frontend', name + '-runner']
    group = os.getenv('BROWSER_QA_GROUP', '')
    if group not in {'', 'accessibility', 'business', 'auth-final'}:
        raise ValueError('Unsupported browser group')
    selection = (' --grep "responsive accessibility"' if group == 'accessibility'
                 else ' --grep-invert "responsive accessibility|S12 generic registration"' if group == 'business'
                 else ' --grep "S12 generic registration"' if group == 'auth-final' else '')
    def docker(*args, **kwargs):
        return subprocess.run(['docker', *args], check=True, **kwargs)
    try:
        docker('network', 'create', name, stdout=subprocess.DEVNULL)
        docker('run', '-d', '--name', containers[0], '--network', name, '--network-alias', 'backend',
               '--tmpfs', '/app/data', '--mount', f'type=bind,source={backend / "scripts"},target=/app/scripts,readonly',
               '-e', 'DATABASE_URL=sqlite:///./data/browser-e2e.db',
                '-e', 'AUTH_ABUSE_ENABLED=' + ('true' if os.getenv('BROWSER_QA_AUTH_ABUSE') == '1' else 'false'),
                '-e', 'PUBLIC_REGISTRATION_ENABLED=' + ('true' if group == 'auth-final' else 'false'),
               '-e', 'SESSION_SECRET=isolated-browser-tests-only', 'typography-s04-backend',
               'sh', '-c', '.venv/bin/python -m scripts.browser_fixture && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000',
               stdout=subprocess.DEVNULL)
        docker('run', '-d', '--name', containers[1], '--network', name, '--network-alias', 'frontend',
               'typography-s04-frontend', 'sh', '-c',
               "sed -i 's/listen 80;/listen 8081;/' /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'",
               stdout=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while True:
            ready = subprocess.run(['docker', 'exec', containers[0], '.venv/bin/python', '-c',
                                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ready.returncode == 0:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Isolated backend failed to start')
            time.sleep(1)
        docker('run', '--name', containers[2], '--network', name, '--ipc=host',
               '--mount', f'type=bind,source={frontend},target=/source,readonly',
               '-e', 'BROWSER_QA_URL=http://frontend:8081',
               '-e', 'BROWSER_QA_SYNTHETIC_ORPHANS=1',
               '-e', 'BROWSER_QA_REGISTRATION=' + ('1' if group == 'auth-final' else '0'),
               'mcr.microsoft.com/playwright:v1.65.1-noble', 'sh', '-c',
               'cp -r /source /tmp/frontend && cd /tmp/frontend && npm ci && npm test && npm run test:e2e -- --reporter=line' + selection,
               timeout=900)
    finally:
        for container in reversed(containers):
            subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, check=False)
        subprocess.run(['docker', 'network', 'rm', name], stdout=subprocess.DEVNULL, check=False)


if __name__ == '__main__':
    main()