"""VM-only full-clone reset and test orchestration; requires Docker and Python 3.

Run from the Compose directory with the backend repository at ./backend.
Never supplies working-database credentials to the QA container.
"""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
from datetime import datetime, timezone


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump', type=Path, required=True)
    parser.add_argument('--confirm', required=True)
    args = parser.parse_args()
    if args.confirm != 'RESET-typography_fullclone_test' or not args.dump.is_file():
        parser.error('Existing dump and explicit clone-reset confirmation required')
    lock = Path('qa-fullclone.lock')
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        parser.error('Another QA run may be active; inspect qa-fullclone.lock before removing it')
    try:
        execute(args)
    finally:
        lock.rmdir()


def execute(args):
    compose = ['docker', 'compose']
    mysql = run(compose + ['ps', '-q', 'mysql'], capture_output=True, text=True).stdout.strip()
    backend = run(compose + ['ps', '-q', 'backend'], capture_output=True, text=True).stdout.strip()
    if not mysql or not backend:
        raise RuntimeError('Running backend and mysql Compose services required')
    mysql_info = json.loads(run(['docker', 'inspect', mysql], capture_output=True, text=True).stdout)[0]
    network = next(iter(mysql_info['NetworkSettings']['Networks']))
    user, password = 'qa_' + secrets.token_hex(6), secrets.token_hex(24)

    def sql(statement):
        return run(['docker', 'exec', '-i', mysql, 'sh', '-c',
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B'],
                   input=statement, capture_output=True, text=True).stdout

    # CHECKSUM is read-only and catches changes beyond row counts. No SQL
    # interpolated here is user supplied; identifiers are fixed or generated.
    baseline_sql = 'CHECKSUM TABLE typography_restored.orders, typography_restored.bills, typography_restored.payments;'
    before = sql(baseline_sql)
    reports = Path('qa-results')
    reports.mkdir(mode=0o700, exist_ok=True)
    for name in ('reset.json', 'tests.json', 'working-integrity.json', 'access-boundary.json'):
        (reports / name).unlink(missing_ok=True)
    dockerfile = '''FROM rework-backend
USER root
RUN apt-get update && apt-get install -y --no-install-recommends default-mysql-client && rm -rf /var/lib/apt/lists/*
COPY app/mysql_test_guard.py app/mysql_clone_reset.py app/run_mysql_tests.py /app/app/
COPY app/reports.py /app/app/
COPY tests/test_mysql_runtime.py /app/tests/
'''
    run(['docker', 'build', '-f', '-', '-t', 'rework-qa', 'backend'], input=dockerfile, text=True)
    sql(f"CREATE USER '{user}'@'%' IDENTIFIED BY '{password}'; GRANT ALL PRIVILEGES ON `typography\\_fullclone\\_test`.* TO '{user}'@'%';")
    try:
        with tempfile.TemporaryDirectory(prefix='mysql-qa-') as directory:
            directory = Path(directory)
            defaults = directory / 'client.cnf'
            # Isolated Docker-network QA only; do not reuse for external MySQL.
            defaults.write_text(f'[client]\nhost=mysql\nssl=0\nuser={user}\npassword={password}\n')
            defaults.chmod(0o600)
            env = directory / 'qa.env'
            env.write_text(f'MYSQL_TEST_URL=mysql+pymysql://{user}:{password}@mysql/typography_fullclone_test\n'
                           'DATABASE_URL=sqlite:///:memory:\nMYSQL_TEST_DEFAULTS_FILE=/run/qa/client.cnf\n')
            env.chmod(0o600)
            common = ['docker', 'run', '--rm', '--network', network, '--env-file', str(env),
                      '-v', f'{directory}:/run/qa:ro', '-v', f'{args.dump.resolve()}:/dump.sql:ro',
                      '-v', f'{reports.resolve()}:/reports', 'rework-qa', '.venv/bin/python']
            with (reports / 'reset.log').open('w') as log:
                run(common + ['-m', 'app.mysql_clone_reset', '/dump.sql', '--confirm', args.confirm,
                              '--report', '/reports/reset.json'], stdout=log, stderr=subprocess.STDOUT)
            # Prove the account cannot even read the working database.
            denied = subprocess.run(['docker', 'run', '--rm', '--network', network, '--env-file', str(env),
                                     '-v', f'{directory}:/run/qa:ro', 'rework-qa', 'mysql',
                                     '--defaults-extra-file=/run/qa/client.cnf', '-e',
                                     'SELECT id FROM typography_restored.orders LIMIT 1'], capture_output=True)
            if denied.returncode == 0 or not any(code in denied.stderr for code in (b'ERROR 1044', b'ERROR 1142')):
                raise RuntimeError('Working database denial was not verified')
            (reports / 'access-boundary.json').write_text(json.dumps({
                'working_database_access_denied': True,
                'test_database': 'typography_fullclone_test'}, indent=2))
            with (reports / 'tests.log').open('w') as log:
                run(common + ['-m', 'app.run_mysql_tests', '--report', '/reports/tests.json'], stdout=log, stderr=subprocess.STDOUT)
    finally:
        sql(f"DROP USER IF EXISTS '{user}'@'%';")
        after = sql(baseline_sql)
        (reports / 'working-integrity.json').write_text(json.dumps({
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'unchanged': before == after, 'before': before, 'after': after}, indent=2))
        if before != after:
            raise RuntimeError('Working table checksums changed during QA; investigate concurrent activity')
    print('Full clone reset and suite passed; working table checksums unchanged. See qa-results/.')


if __name__ == '__main__':
    main()