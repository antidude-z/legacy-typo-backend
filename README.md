# Typography backend

## Schema drift checks

Run `uv run python -m app.schema_audit --output data/schema-drift.json` for a
read-only model/database inventory of types, decimal precision, nullability,
defaults, indexes, uniqueness, and foreign keys. Client-side defaults are listed
separately from database defaults; differences are not automatically repaired.
From the VM Compose directory, `python3 backend/scripts/mysql_schema_qa.py`
checks tracked upgrades and their repeat execution using a clone-only account.
Results are in `qa-results/schema-drift.json`; working-table checksum checks are
in `qa-results/schema-working-integrity.json`.

Migration `2026-11-19-06` preserves decimal work quantities in existing SQLite
tables and permits non-order history rows without an order ID. SQLite rebuilds
retain extra columns, indexes, and triggers and refuse incoming foreign keys;
back up custom deployments before upgrading. MySQL upgrades widen markup-type
storage, temporarily relaxing legacy zero-date checks only for the DDL session.

Synchronize deployments through GitHub: push backend `fix/mysql-runtime` and
frontend `main`, then pull the matching branches with `git pull --ff-only` on
the VM. Preserve local VM edits before pulling. Updating a checkout does not
rebuild running containers or apply upgrades to the working database.

## MySQL runtime regression checks

The image installs the frozen `uv.lock`, including PyMySQL RSA authentication
support. Migration `2026-11-19-01` adds deployed-schema compatibility columns
and maps order history identifiers; it temporarily relaxes zero-date validation
only for its own DDL connection and restores the original SQL mode afterward.

Set `MYSQL_TEST_URL` to a dedicated database named `typography_runtime_test`
or `typography_imported_test`,
then run `uv run python -m unittest tests.test_mysql_runtime -v`. The test
creates fixtures and leaves them in that test database for inspection. Never
use a business database. Without this variable the MySQL integration test skips.

For the existing full clone, set `MYSQL_TEST_URL` to the dedicated
`typography_fullclone_test` database and run `uv run python -m app.run_mysql_tests`.
The runner checks the target name and configured `DATABASE_URL`, reports test
results without printing credentials, and refuses skipped tests. It mutates the
clone and does not create or reset it. Use separate test credentials restricted
to that database; hostname aliases cannot be reliably detected by the guard.

### Repeatable full-data QA on the Docker VM

From the Compose directory (`/root/rework` on the validation VM):

```sh
python3 backend/scripts/mysql_fullclone_qa.py \
  --dump /root/legacy/dump_full.sql \
  --confirm RESET-typography_fullclone_test
```

This uses the existing `rework-backend` image and running `backend`/`mysql`
services. It builds a separate QA image, creates a temporary clone-only MySQL
account, resets **only** `typography_fullclone_test`, imports the read-only dump,
and executes the integration suite (including compatibility migrations).
The application services are not rebuilt or restarted. Expect several minutes
and sufficient disk for another database copy. The VM's working database is
`typography_restored`; do not repurpose the hard-coded test database for business.

Logs and JSON diagnostics are in `qa-results/`: `reset.log`, `reset.json`,
`tests.log`, `tests.json`, and `working-integrity.json`. Credentials are temporary,
mode 0600, and removed with the test account in `finally`. A directory lock
prevents concurrent runs. After abrupt process termination, inspect for surviving
QA containers/accounts before removing `qa-fullclone.lock` and retrying.

Both commands reject global/cross-database grants. The workflow also proves
working-database access is denied and compares working orders/bills/payments
checksums before and after. Concurrent business edits can change checksums and
fail this check; schedule a quiet validation window. Checksums cover these three
tables only; restricted database grants provide the mutation boundary.

Standalone reset is available via `python -m app.mysql_clone_reset DUMP
--confirm RESET-typography_fullclone_test --report reset.json`, with
`MYSQL_TEST_DEFAULTS_FILE` pointing to a protected MySQL client option file.
Dump SQL is executed only by this opt-in command using clone-restricted grants;
the reset is destructive/nontransactional and may leave a partial clone on error.
Never use production credentials. The QA-only client disables TLS inside the
isolated Docker network; this is not an external MySQL connection configuration.

The imported-schema test uses a schema-only copy of the historical database,
not a full historical-data clone. MySQL compatibility upgrades permit NULL in
columns declared optional by the ORM and in obsolete polymorphic action fields;
existing values are retained. Back up MySQL before applying these DDL changes,
which are not transactional on legacy MyISAM tables.


FastAPI/SQLAlchemy backend for the migrated typography application. SQLite is
the local default; production deployment should use MySQL populated from the
preserved legacy dump.

## Requirements

- Python 3.14 and `uv`.
- Node 26 for the frontend.
- Docker Engine and Compose for container deployment.

## Local development

```powershell
cd rework\backend
uv sync
uv run python -m app.migrate upgrade
uv run python -m app.bootstrap
uv run uvicorn app.main:app --reload
```

The default database is `data/typography.db`. Set `DATABASE_URL` to use another
database. Never use the working SQLite file as an importer target.

## Production MySQL migration

`rework/dump_full.sql` is the legacy source dump. The safe `app.import_dump`
converter is for disposable SQLite analysis only; it never executes SQL and is
not the production MySQL import procedure.

1. Back up the target MySQL server and create a disposable import database.
2. Confirm MySQL version, charset, timezone, credentials, and empty target.
3. Import `dump_full.sql` with the approved MySQL client/server procedure.
4. Exclude Laravel bookkeeping decisions from application data migration.
5. Review row counts, orphan relationships, dates, decimals, soft deletes, and
   serialized calculation fields using the reconciliation/audit tools.
6. Point the backend at the validated database:

```text
DATABASE_URL=mysql+pymysql://typography:password@mysql:3306/typography
```

7. Apply tracked upgrades and idempotent catalog initialization:

```powershell
uv run python -m app.migrate upgrade
uv run python -m app.bootstrap
uv run python -m app.diagnostics --output data/diagnostics.json
```

8. Run the backend/frontend suites and complete the browser, report-output,
   backup/rollback, and cutover checks in `rework/MIGRATION.md`.

The application never imports or overwrites historical data at startup.

## Controlled dump analysis

```powershell
uv run python -m app.schema_inventory ..\dump_full.sql --output docs\schema-inventory.json
uv run python -m app.reconcile_dump ..\dump_full.sql --output docs\dump-reconciliation.json
uv run python -m app.import_dump ..\dump_full.sql --target ..\data\dump-test.db --dry-run --limit 100
uv run python -m app.validate_import ..\data\dump-test.db --output docs\import-validation.json
uv run python -m app.historical_audit ..\data\dump-test.db --output docs\historical-audit.json
```

These tools use disposable SQLite files and are not a production import path.

## Docker deployment

From `rework`:

```powershell
docker compose config --quiet
docker compose up --build
```

The default stack uses persistent SQLite and serves the frontend on port 8080;
the backend is on port 8000. To run the MySQL profile:

```powershell
docker compose --profile mysql up --build
```

Set `DATABASE_URL` and MySQL credentials through the deployment environment.
Never commit secrets. Validate health, persistence, restart, proxying, and
rollback before production cutover.

## Validation

```powershell
uv run python -m unittest discover -s tests -q
cd ..\frontend
npm install
npm test
npm run build
```

The backend and frontend are separate Git repositories. The full migration and
retirement checklist is `rework/MIGRATION.md`.