"""Exercise clone-only import, backup, upgrades, restore rollback and re-upgrade.

Run from the VM Compose directory. Never restarts the working application.
"""
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    lock = Path('qa-fullclone.lock')
    lock.mkdir(mode=0o700)
    try:
        execute()
    finally:
        lock.rmdir()


def execute():
    dump = Path('/root/legacy/dump_full.sql')
    if not dump.is_file() or shutil.disk_usage('.').free < 1_500_000_000:
        raise RuntimeError('Source dump and at least 1.5 GB free space required')
    mysql = run(['docker', 'compose', 'ps', '-q', 'mysql'], capture_output=True, text=True).stdout.strip()
    network = next(iter(json.loads(run(['docker', 'inspect', mysql], capture_output=True, text=True).stdout)[0]['NetworkSettings']['Networks']))

    def sql(statement):
        return run(['docker', 'exec', '-i', mysql, 'sh', '-c',
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B'],
                   input=statement, capture_output=True, text=True).stdout

    check = 'CHECKSUM TABLE typography_restored.orders, typography_restored.bills, typography_restored.payments;'
    before = sql(check)
    output = Path('qa-results') / ('recovery-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(mode=0o700, parents=True)
    user, password = 'recoveryqa_' + secrets.token_hex(5), secrets.token_hex(24)
    sql(f"CREATE USER '{user}'@'%' IDENTIFIED BY '{password}'; GRANT ALL PRIVILEGES ON `typography\\_fullclone\\_test`.* TO '{user}'@'%';")
    try:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            defaults = directory / 'client.cnf'
            defaults.write_text(f'[client]\nhost=mysql\nssl=0\nuser={user}\npassword={password}\n')
            defaults.chmod(0o600)
            env = directory / 'qa.env'
            env.write_text(f'DATABASE_URL=mysql+pymysql://{user}:{password}@mysql/typography_fullclone_test\nMYSQL_TEST_DEFAULTS_FILE=/run/qa/client.cnf\n')
            env.chmod(0o600)
            common = ['docker', 'run', '--rm', '--network', network, '--env-file', str(env),
                      '-v', f'{directory}:/run/qa:ro', '-v', f'{dump}:/dump.sql:ro',
                      '-v', f'{Path("backend/app").resolve()}:/app/app:ro',
                      '-v', f'{output.resolve()}:/results', 'rework-qa', '.venv/bin/python']

            def execute_python(arguments, log):
                with (output / log).open('w') as stream:
                    run(common + arguments, stdout=stream, stderr=subprocess.STDOUT)

            snapshot = '''import json
from pathlib import Path
from sqlalchemy import text
from app.db import engine
from app.mysql_test_guard import verify_test_database
import os
verify_test_database(os.environ['DATABASE_URL'])
result={}
with engine.connect() as c:
 tables=list(c.scalars(text('SHOW TABLES')))
 for table in sorted(tables):
  quoted='`'+table.replace('`','``')+'`'
  result[table]={'rows':c.scalar(text('SELECT COUNT(*) FROM '+quoted)), 'checksum':c.execute(text('CHECKSUM TABLE '+quoted)).first()[1], 'ddl':c.execute(text('SHOW CREATE TABLE '+quoted)).first()[1]}
 if 'schema_migrations' in tables:
  result['_versions']=list(c.scalars(text('SELECT version FROM schema_migrations ORDER BY version')))
Path('/results/NAME.json').write_text(json.dumps(result,indent=2,default=str))
'''

            def snap(name):
                execute_python(['-c', snapshot.replace('NAME', name)], name + '.log')

            execute_python(['-m', 'app.mysql_clone_reset', '/dump.sql', '--confirm', 'RESET-typography_fullclone_test', '--report', '/results/import.json'], 'import.log')
            snap('original')
            execute_python(['-m', 'app.mysql_recovery', 'backup', '/results/before.sql', '--report', '/results/backup.json'], 'backup.log')
            upgrade = '''from app.db import engine
from app.bootstrap import initialize_database
from app.schema import apply_migrations
initialize_database(engine)
assert apply_migrations(engine)==[]
print('Upgrade, seed, repeat upgrade passed')
'''
            execute_python(['-c', upgrade], 'upgrade.log')
            snap('upgraded')
            expected = json.loads((output / 'backup.json').read_text())['backup_sha256']
            execute_python(['-m', 'app.mysql_recovery', 'restore', '/results/before.sql', '--sha256', expected,
                            '--confirm', 'RESET-typography_fullclone_test', '--report', '/results/restore.json'], 'restore.log')
            snap('restored')
            original = json.loads((output / 'original.json').read_text())
            restored = json.loads((output / 'restored.json').read_text())
            if original != restored:
                raise RuntimeError('Restored row counts, checksums, DDL or versions differ')
            execute_python(['-c', upgrade], 'reupgrade.log')
            snap('reupgraded')
            upgraded = json.loads((output / 'upgraded.json').read_text())
            reupgraded = json.loads((output / 'reupgraded.json').read_text())
            # Migration application timestamps intentionally differ on re-upgrade.
            comparable = lambda x: {k: v for k, v in x.items() if k not in ('schema_migrations', 'schema_versions')}
            if comparable(upgraded) != comparable(reupgraded):
                raise RuntimeError('Re-upgrade business snapshot differs')
            (output / 'result.json').write_text(json.dumps({'restore_equal': True, 'reupgrade_equal': True,
                'tables': len(original), 'backup_sha256': expected}, indent=2))
            # Validated backup is expendable clone data; keep diagnostics, avoid filling VM.
            (output / 'before.sql').unlink()
    finally:
        sql(f"DROP USER IF EXISTS '{user}'@'%';")
        unchanged = before == sql(check)
        (output / 'working-integrity.json').write_text(json.dumps({'unchanged': unchanged}))
        if not unchanged:
            raise RuntimeError('Working checksums changed; investigate concurrent activity')
    print(f'Recovery exercise passed: {output}')


if __name__ == '__main__':
    main()