"""Run local Playwright with explicitly owned servers and bounded Windows cleanup.

Avoids Playwright's shell-based Windows webServer teardown. Never reuses a server
or accepts a database URL; only scripts.browser_fixture's disposable DB is used.
"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


def main():
    backend = Path(__file__).resolve().parents[1]
    frontend = backend.parent / 'frontend'
    if not frontend.is_dir():
        frontend = backend.parent / 'legacy-typo-frontend'
    if os.getenv('BROWSER_QA_URL'):
        raise RuntimeError('Local harness cannot target remote QA')
    for port in (8000, 5173):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))  # Fail closed on occupied ports.
    env = {**os.environ, 'DATABASE_URL': 'sqlite:///' + (backend / 'data/browser-e2e.db').as_posix(),
           'SESSION_SECRET': 'isolated-browser-tests-only', 'BROWSER_QA_MANAGED_LOCAL': '1'}
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node is required')
    subprocess.run([sys.executable, '-m', 'scripts.browser_fixture'], cwd=backend, env=env, check=True)
    children = []
    logs = []
    try:
        for name, command, cwd in (
            ('backend', [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], backend),
            ('frontend', [node, str(frontend / 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1'], frontend),
        ):
            log = open(backend / 'data' / f'browser-qa-{name}.log', 'w', encoding='utf-8')
            logs.append(log)
            children.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT))
        for port, path in ((8000, '/health'), (5173, '/')):
            deadline = time.monotonic() + 60
            while True:
                if any(child.poll() is not None for child in children):
                    raise RuntimeError('QA server exited; inspect data/browser-qa-*.log')
                try:
                    with urlopen(f'http://127.0.0.1:{port}{path}', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError('QA server startup timed out')
                time.sleep(0.2)
        command = [node, str(frontend / 'node_modules/@playwright/test/cli.js'), 'test', *sys.argv[1:]]
        return subprocess.run(command, cwd=frontend, env=env, timeout=600).returncode
    finally:
        for child in reversed(children):
            if child.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                else:
                    child.terminate()
                child.wait(timeout=20)
        for log in logs:
            log.close()


if __name__ == '__main__':
    raise SystemExit(main())