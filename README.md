# Typography backend

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