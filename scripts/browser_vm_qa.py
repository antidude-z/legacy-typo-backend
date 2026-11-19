"""Start/stop an isolated browser deployment against the disposable MySQL clone.

Run from /root/rework. Reset the clone with mysql_fullclone_qa.py first.
Never supplies working DB credentials to the application containers.
"""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

STATE = Path('qa-results/browser-state.json')
LOCK = Path('qa-fullclone.lock')
BACKEND = 'typography-browser-backend'
FRONTEND = 'typography-browser-frontend'
CHECKSUM = 'CHECKSUM TABLE typography_restored.orders, typography_restored.bills, typography_restored.payments;'


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def mysql_container():
    return run(['docker', 'compose', 'ps', '-q', 'mysql'], capture_output=True, text=True).stdout.strip()


def sql(container, statement):
    return run(['docker', 'exec', '-i', container, 'sh', '-c',
                'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B'],
               input=statement, capture_output=True, text=True).stdout


def stop():
    if not STATE.exists():
        raise RuntimeError('No owned browser QA state to clean up')
    state = json.loads(STATE.read_text())
    try:
        for name in (FRONTEND, BACKEND):
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, check=False)
        user = state['user']
        if not user.startswith('bqa_') or not user[4:].isalnum():
            raise RuntimeError('Invalid recorded account')
        sql(state['mysql'], f"DROP USER IF EXISTS '{user}'@'%';")
        after = sql(state['mysql'], CHECKSUM)
        result = {'working_checksums_unchanged': state['before'] == after,
                  'before': state['before'], 'after': after, 'containers_removed': True}
        Path('qa-results/browser-integrity.json').write_text(json.dumps(result, indent=2))
        if not result['working_checksums_unchanged']:
            raise RuntimeError('Working checksums changed; investigate concurrent writes')
    finally:
        STATE.unlink(missing_ok=True)
        LOCK.rmdir()


def start():
    if STATE.exists():
        raise RuntimeError('Existing browser deployment must be stopped first')
    LOCK.mkdir(mode=0o700)
    try:
        mysql = mysql_container()
        info = json.loads(run(['docker', 'inspect', mysql], capture_output=True, text=True).stdout)[0]
        network = next(iter(info['NetworkSettings']['Networks']))
        user, password = 'bqa_' + secrets.token_hex(6), secrets.token_hex(24)
        before = sql(mysql, CHECKSUM)
        sql(mysql, f"CREATE USER '{user}'@'%' IDENTIFIED BY '{password}'; GRANT ALL PRIVILEGES ON `typography\\_fullclone\\_test`.* TO '{user}'@'%';")
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps({'mysql': mysql, 'user': user, 'before': before}))
        STATE.chmod(0o600)
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / 'qa.env'
            env.write_text(f'DATABASE_URL=mysql+pymysql://{user}:{password}@mysql/typography_fullclone_test\n'
                           f'MYSQL_TEST_URL=mysql+pymysql://{user}:{password}@mysql/typography_fullclone_test\n'
                           f'SESSION_SECRET={secrets.token_hex(32)}\n')
            env.chmod(0o600)
            common = ['docker', 'run', '--network', network, '--env-file', str(env),
                      '-v', f'{Path("backend/app").resolve()}:/app/app:ro',
                      '-v', f'{Path("backend/scripts").resolve()}:/app/scripts:ro']
            run(common + ['--rm', 'rework-backend', '.venv/bin/python', '-m', 'scripts.browser_fixture', '--mysql-clone'])
            run(common + ['-d', '--name', BACKEND, '--network-alias', BACKEND, 'rework-backend'])
        for _ in range(40):
            check = subprocess.run(['docker', 'exec', BACKEND, '.venv/bin/python', '-c',
                                    'import urllib.request; urllib.request.urlopen("http://localhost:8000/health")'], capture_output=True)
            if check.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('QA backend did not start')
        nginx = Path('qa-results/browser-nginx.conf')
        nginx.write_text(Path('frontend/nginx.conf').read_text().replace('http://backend:8000', f'http://{BACKEND}:8000'))
        run(['docker', 'run', '-d', '--name', FRONTEND, '--network', network, '-p', '8081:80',
             '-v', f'{Path("frontend/dist").resolve()}:/usr/share/nginx/html:ro',
             '-v', f'{nginx.resolve()}:/etc/nginx/conf.d/default.conf:ro', 'rework-frontend'])
        print('Isolated browser QA ready on port 8081. Stop it after testing.')
    except Exception:
        if STATE.exists():
            stop()
        else:
            LOCK.rmdir()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop'])
    args = parser.parse_args()
    start() if args.action == 'start' else stop()