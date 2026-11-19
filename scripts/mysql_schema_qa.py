"""Run model drift/repeat-upgrade checks only against the disposable clone."""
import json
from pathlib import Path
import secrets
import subprocess
import tempfile


def main():
    lock = Path('qa-fullclone.lock')
    lock.mkdir(mode=0o700)
    try:
        execute()
    finally:
        lock.rmdir()


def execute():
    def run(args, **kwargs):
        return subprocess.run(args, check=True, **kwargs)
    mysql = run(['docker', 'compose', 'ps', '-q', 'mysql'], capture_output=True, text=True).stdout.strip()
    network = next(iter(json.loads(run(['docker', 'inspect', mysql], capture_output=True, text=True).stdout)[0]['NetworkSettings']['Networks']))
    def sql(statement):
        return run(['docker', 'exec', '-i', mysql, 'sh', '-c', 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B'], input=statement, capture_output=True, text=True).stdout
    check = 'CHECKSUM TABLE typography_restored.orders, typography_restored.bills, typography_restored.payments;'
    before = sql(check)
    user, password = 'schemaqa_' + secrets.token_hex(5), secrets.token_hex(24)
    sql(f"CREATE USER '{user}'@'%' IDENTIFIED BY '{password}'; GRANT ALL PRIVILEGES ON `typography\\_fullclone\\_test`.* TO '{user}'@'%';")
    output = Path('qa-results'); output.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / 'qa.env'
            env.write_text(f'DATABASE_URL=mysql+pymysql://{user}:{password}@mysql/typography_fullclone_test\n')
            env.chmod(0o600)
            code = '''import json,os
from pathlib import Path
from app.db import engine
from app.mysql_test_guard import verify_test_database
from app.schema import apply_migrations
from app.schema_audit import audit_schema
verify_test_database(os.environ['DATABASE_URL'])
before=audit_schema(engine)
applied=apply_migrations(engine)
repeated=apply_migrations(engine)
assert repeated == []
after=audit_schema(engine)
Path('/results/schema-drift.json').write_text(json.dumps({'before':before,'applied':applied,'repeat':repeated,'after':after},indent=2,default=str))
print(json.dumps({'applied':applied,'repeat':repeated,'differences':{name:row.get('differences',[]) for name,row in after['tables'].items() if row.get('differences') or row.get('missing_table')}}))
'''
            run(['docker', 'run', '--rm', '--network', network, '--env-file', str(env),
                 '-v', f'{Path("backend/app").resolve()}:/app/app:ro',
                 '-v', f'{output.resolve()}:/results', 'rework-backend', '.venv/bin/python', '-c', code])
    finally:
        sql(f"DROP USER IF EXISTS '{user}'@'%';")
        unchanged = before == sql(check)
        (output / 'schema-working-integrity.json').write_text(json.dumps({'unchanged': unchanged}))
        if not unchanged:
            raise RuntimeError('Working checksums changed; investigate concurrent activity')


if __name__ == '__main__':
    main()