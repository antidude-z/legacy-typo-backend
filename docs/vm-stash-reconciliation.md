# VM stash reconciliation

Reviewed `pre-github-sync-schema-reconciliation` on backend `fix/mysql-runtime`
and frontend `main`. Comparisons ignore CRLF/LF differences; stash snapshots are
not applied over newer commits.

## Backend

| Stashed content | Disposition |
| --- | --- |
| accounting_bills, bootstrap, main, reference_customers, reports, run_mysql_tests, mysql_fullclone_qa, test_mysql_runtime | Functional contents already identical to committed versions. |
| models | Current version additionally permits NULL non-order history IDs; retain current version. |
| schema | Current version additionally contains tracked SQLite/markup reconciliation; retain current version. |
| schema_audit, browser_vm_qa, mysql_schema_qa, test_session_security | Former untracked files are now committed and identical. |
| browser_fixture | Current version also includes isolated orphan-selector fixtures; retain current version. |
| Dockerfile.vm | Superseded by Dockerfile plus frozen uv.lock with RSA authentication dependency; do not restore ad-hoc pip installation. |
| Dockerfile.qa | Superseded by mysql_fullclone_qa.py's QA build, which copies current application modules and tests. |
| mysql-compat.py | Superseded by tracked schema migrations; do not restore unguarded, non-repeatable ALTER statements. |
| mysql-api-smoke.py | Superseded by guarded test_mysql_runtime and real-session tests. |
| mysql-read-check.py, mysql-schema-check.py | Superseded by schema_audit, historical_audit, diagnostics and guarded MySQL tests. |
| uv.lock.upload | Empty interrupted upload; frozen uv.lock is authoritative. |

No unique functional change remains solely in the reviewed stash. No credentials,
database contents, uploaded lockfile fragments, or obsolete deployment helpers
are introduced into version control by this reconciliation.

## Frontend

The sole stash delta was the Nginx report-route regex, already identical to the
committed nginx.conf. The current version keeps payroll SPA routes out of the
report-generation proxy. Retain the current version.

## Synchronization

Push the current branch to origin, then pull the same branch using `--ff-only`
on the VM. Verify identical commit IDs and clean tracked/untracked status before
dropping the specifically reviewed stash. Do not use blanket stash clearing or
restore older helper files. Checkout synchronization alone must not restart the
service, apply working-database migrations, or change deployed container images.