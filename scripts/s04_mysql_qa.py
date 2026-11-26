"""Run S04/S05 on owned disposable Docker MySQL; never accepts a working URL."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from uuid import uuid4


def docker(*args, **kwargs):
    return subprocess.run(['docker', *args], check=True, **kwargs)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finding', choices=('S04', 'S05', 'S06'), default='S04')
    finding = parser.parse_args().finding
    backend = Path(__file__).resolve().parents[1]
    name = 'typography-s04-qa-' + uuid4().hex[:12]
    password = secrets.token_hex(24)
    env = {**os.environ, 'MYSQL_ROOT_PASSWORD': secrets.token_hex(24),
           'MYSQL_DATABASE': 'typography_runtime_test', 'MYSQL_USER': 's04qa',
           'MYSQL_PASSWORD': password}
    try:
        docker('run', '-d', '--name', name, '--tmpfs', '/var/lib/mysql',
               '-p', '127.0.0.1::3306', '-e', 'MYSQL_ROOT_PASSWORD', '-e', 'MYSQL_DATABASE',
               '-e', 'MYSQL_USER', '-e', 'MYSQL_PASSWORD', 'mysql:8.0', env=env,
               stdout=subprocess.DEVNULL)
        info = json.loads(docker('inspect', name, capture_output=True, text=True).stdout)[0]
        port = info['NetworkSettings']['Ports']['3306/tcp'][0]['HostPort']
        url = f'mysql+pymysql://s04qa:{password}@127.0.0.1:{port}/typography_runtime_test'
        from app.mysql_test_guard import verify_test_database
        deadline = time.monotonic() + 180
        while True:
            try:
                verify_test_database(url)
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise RuntimeError('Isolated MySQL startup/guard timed out') from None
                time.sleep(2)
        for storage in ('InnoDB', 'MyISAM'):
            print(f'{finding} isolated {storage}', flush=True)
            test_env = {**os.environ, 'MYSQL_ADMIN_TEST_URL': url,
                        'DATABASE_URL': 'sqlite://', 'S04_MYSQL_ENABLED': '1',
                        'S03_MYSQL_ENGINE': storage}
            test_env[f'{finding}_MYSQL_ENABLED'] = '1'
            suite = ('tests.test_review_s04_mysql.MySQLDelegationReviewTests' if finding == 'S04'
                     else 'tests.test_review_s05_mysql.MySQLReportAuthorizationReviewTests' if finding == 'S05'
                     else 'tests.test_review_s06_mysql.MySQLAccountingDeletionTests')
            subprocess.run([sys.executable, '-W', 'error', '-m', 'unittest',
                            suite, '-v'],
                           cwd=backend, env=test_env, check=True, timeout=300)
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, check=False)


if __name__ == '__main__':
    main()