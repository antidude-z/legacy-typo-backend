"""Run the opt-in MySQL suite against an existing dedicated test database."""
import json
import os
import sys
import unittest

from app.mysql_test_guard import verify_test_database


def main() -> int:
    url = os.getenv('MYSQL_TEST_URL')
    if not url:
        print('MYSQL_TEST_URL is required', file=sys.stderr)
        return 2
    try:
        info = verify_test_database(url, os.getenv('DATABASE_URL'))
    except Exception as exc:
        print(f'MySQL test preflight failed: {type(exc).__name__}', file=sys.stderr)
        return 2
    print(json.dumps({'preflight': 'passed', **info}), flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_mysql_runtime.MySQLRuntimeTests')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'tests_run': result.testsRun, 'failures': len(result.failures),
                      'errors': len(result.errors), 'skipped': len(result.skipped)}))
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())