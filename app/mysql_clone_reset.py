"""Safely reset the dedicated MySQL test clone from an existing SQL dump.

The MySQL client reads credentials from MYSQL_TEST_DEFAULTS_FILE, never argv.
The credentials must have privileges limited to the dedicated test database.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

TARGET = 'typography_fullclone_test'
CONFIRMATION = 'RESET-typography_fullclone_test'


def reset_clone(dump: Path, defaults: Path, confirmation: str) -> None:
    if confirmation != CONFIRMATION:
        raise ValueError('Explicit test-clone reset confirmation required')
    if not dump.is_file() or not defaults.is_file():
        raise ValueError('Dump and MySQL defaults file must exist')
    # A dump can contain USE, CREATE DATABASE, or other arbitrary SQL. Importing
    # it with an account restricted to TARGET is essential: a client-side name
    # check is not a database security boundary.
    client = ['mysql', f'--defaults-extra-file={defaults}']
    ddl = f'DROP DATABASE IF EXISTS `{TARGET}`; CREATE DATABASE `{TARGET}` CHARACTER SET utf8mb4;'
    subprocess.run(client + ['--execute', ddl], check=True)
    with dump.open('rb') as source:
        subprocess.run(client + [TARGET], stdin=source, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dump', type=Path)
    parser.add_argument('--confirm', required=True)
    args = parser.parse_args()
    defaults = os.getenv('MYSQL_TEST_DEFAULTS_FILE')
    if not defaults:
        parser.error('MYSQL_TEST_DEFAULTS_FILE is required')
    try:
        reset_clone(args.dump, Path(defaults), args.confirm)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Clone reset failed: {type(exc).__name__}; target may be incomplete', file=sys.stderr)
        return 1
    print(f'Restored dedicated test database: {TARGET}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())