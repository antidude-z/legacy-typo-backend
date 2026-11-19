"""Fresh isolated Compose build/start/restart/persistence checks; no working volumes."""
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    output = Path('qa-results/compose'); output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        env = Path(directory) / 'qa.env'
        env.write_text(f'SESSION_SECRET={secrets.token_hex(32)}\nMYSQL_PASSWORD={secrets.token_hex(24)}\nMYSQL_ROOT_PASSWORD={secrets.token_hex(24)}\nFRONTEND_PORT=8082\nFRONTEND_BIND=127.0.0.1\nAPP_URL=http://127.0.0.1:8082\n')
        env.chmod(0o600)
        base = ['docker', 'compose', '--project-name', 'typography_deployqa', '--project-directory', str(Path.cwd()),
                '--env-file', str(env), '-f', 'backend/deploy/compose.yaml', '-f', 'backend/deploy/mysql.yaml', '--profile', 'mysql']
        # Refuse to reuse any state; never attach a working or external volume.
        if run(base + ['ps', '-aq'], capture_output=True, text=True).stdout.strip():
            raise RuntimeError('QA containers already exist; inspect before continuing')
        volumes = run(['docker', 'volume', 'ls', '-q', '--filter', 'label=com.docker.compose.project=typography_deployqa'], capture_output=True, text=True).stdout.strip()
        if volumes:
            raise RuntimeError('QA volumes already exist; inspect before continuing')
        result = {}
        try:
            run(base + ['config', '--quiet'])
            with (output / 'build.log').open('w') as log:
                run(base + ['build'], stdout=log, stderr=subprocess.STDOUT)
            with (output / 'startup.log').open('w') as log:
                run(base + ['up', '-d', '--wait', '--wait-timeout', '300'], stdout=log, stderr=subprocess.STDOUT)
            def sql(statement):
                return run(base + ['exec', '-T', 'mysql', 'sh', '-c',
                    'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" "$MYSQL_DATABASE" -N -B'],
                    input=statement, capture_output=True, text=True).stdout.strip()
            sql('CREATE TABLE deployment_probe (id INT PRIMARY KEY, value VARCHAR(32)); INSERT INTO deployment_probe VALUES (1, "persisted");')

            def http_checks():
                for path in ('/', '/auth/login', '/orders', '/reports/payrolls/create', '/api/session'):
                    with urllib.request.urlopen('http://127.0.0.1:8082' + path, timeout=10) as response:
                        assert response.status == 200, path
                        if path == '/api/session':
                            assert json.load(response)['authenticated'] is False
                try:
                    urllib.request.urlopen('http://127.0.0.1:8082/reports/order_passport/item/1', timeout=10)
                except urllib.error.HTTPError as exc:
                    assert exc.code == 401
                else:
                    raise AssertionError('Unauthenticated report generation was not rejected')
            http_checks()
            run(base + ['restart', 'mysql'])
            run(base + ['up', '-d', '--wait', '--wait-timeout', '180'])
            assert sql('SELECT value FROM deployment_probe WHERE id=1') == 'persisted'
            run(base + ['up', '-d', '--force-recreate', '--wait', '--wait-timeout', '180'])
            assert sql('SELECT value FROM deployment_probe WHERE id=1') == 'persisted'
            http_checks()
            # Nginx must recover when backend restarts without changing its IP.
            run(base + ['restart', 'backend'])
            for attempt in range(30):
                try:
                    http_checks()
                    break
                except Exception:
                    if attempt == 29:
                        raise
                    time.sleep(2)
            result = {'fresh_build': True, 'healthy_startup': True, 'proxy_and_spa': True,
                      'mysql_restart_persistence': True, 'container_recreate_persistence': True,
                      'backend_restart_recovery': True, 'project': 'typography_deployqa'}
        finally:
            with (output / 'containers.log').open('w') as log:
                subprocess.run(base + ['logs', '--no-color', '--tail', '80'], stdout=log, stderr=subprocess.STDOUT)
            # Fixed QA project only; working Compose project/volume untouched.
            run(base + ['down', '--volumes', '--remove-orphans'])
            (output / 'result.json').write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()