"""Clone-only MySQL backup/restore. Use a database-scoped account and stop writers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .mysql_clone_reset import CONFIRMATION, TARGET, reset_clone
from .mysql_test_guard import validate_grants


def backup(destination: Path, defaults: Path) -> dict:
    if not defaults.is_file():
        raise ValueError('Protected MySQL defaults file required')
    if os.name != 'nt' and defaults.stat().st_mode & 0o077:
        raise ValueError('MySQL defaults file must be private')
    if destination.exists():
        raise ValueError('Backup destination already exists')
    grants = subprocess.run(['mysql', f'--defaults-extra-file={defaults}', '--batch', '--raw',
                             '--skip-column-names', '--execute', 'SHOW GRANTS'],
                            check=True, capture_output=True, text=True)
    validate_grants(grants.stdout.splitlines(), TARGET)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.partial')
    # Exclusive creation prevents clobbering another run's in-progress backup.
    with temporary.open('xb') as output:
        temporary.chmod(0o600)
        try:
            subprocess.run(['mysqldump', f'--defaults-extra-file={defaults}',
                            '--lock-tables', '--skip-add-locks', '--no-tablespaces',
                            '--hex-blob', TARGET], stdout=output, check=True)
        except BaseException:
            output.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        if temporary.stat().st_size == 0:
            raise ValueError('Empty backup refused')
        # Hard-link publication is atomic and refuses an existing destination.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    with destination.open('rb') as source:
        checksum = hashlib.file_digest(source, 'sha256').hexdigest()
    return {'database': TARGET, 'backup_sha256': checksum,
            'bytes': destination.stat().st_size, 'status': 'backup_created_restore_not_verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'restore'))
    parser.add_argument('file', type=Path)
    parser.add_argument('--confirm')
    parser.add_argument('--sha256')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    defaults = os.environ.get('MYSQL_TEST_DEFAULTS_FILE')
    if not defaults:
        parser.error('MYSQL_TEST_DEFAULTS_FILE required; never use working credentials')
    if args.report.exists() or args.report.resolve() == args.file.resolve():
        parser.error('New, separate report path required')
    if args.action == 'restore':
        if args.confirm != CONFIRMATION or not args.sha256:
            parser.error('Restore requires explicit clone confirmation and expected SHA-256')
        with args.file.open('rb') as source:
            actual = hashlib.file_digest(source, 'sha256').hexdigest()
        if actual.lower() != args.sha256.lower():
            parser.error('Source checksum mismatch; target not changed')
        result = reset_clone(args.file, Path(defaults), args.confirm)
    else:
        result = backup(args.file, Path(defaults))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()