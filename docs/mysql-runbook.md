# MySQL migration and recovery

## Boundaries

- Never test against the working database (`typography_restored` on the VM).
- Preserve the original dump, its SHA-256, and an independent pre-change backup.
- Use a quiet maintenance window: legacy MyISAM DDL and imports are not transactional.
- Clone commands below accept only `typography_fullclone_test` and a clone-only account.
- No PHP runtime is required or permitted by this procedure.

## 1. Import, upgrade, seed, and validate the clone

From the Compose directory, with running MySQL/backend services and the matching
backend checkout pulled from GitHub:

```sh
sha256sum /root/legacy/dump_full.sql
python3 backend/scripts/mysql_fullclone_qa.py \
  --dump /root/legacy/dump_full.sql --confirm RESET-typography_fullclone_test
```

This creates a temporary database-restricted account, imports the dump, runs
compatibility migrations/catalog initialization in the test suite, and validates
historical reads, calculations, reports, sessions, permissions, and CRUD. It
does not rebuild the working containers. Inspect `qa-results/reset.json`,
`tests.json`, `access-boundary.json`, and `working-integrity.json`; require no
skips/failures and unchanged working-table checksums. The suite mutates its clone.

On failure do not continue to cutover. Inspect the logs and reset the clone
again; do not retry an import into a partially populated database. After abrupt
termination inspect surviving QA containers/accounts before removing the lock.

## 2. Clone backup and restore

Run inside a QA image with the MySQL client, Python dependencies, and current
`app/` available. Set `MYSQL_TEST_DEFAULTS_FILE` to a mode-0600 client option file
containing the clone-only credentials. Do not pass passwords in command arguments.
Keep its lifecycle separate from the automatic QA account, which is removed when
the full-clone script exits. Stop clone writers and retain enough free disk for
both the database and its backup.

```sh
python -m app.mysql_recovery backup /backups/clone-before-upgrade.sql \
  --report /backups/clone-before-upgrade.json
sha256sum /backups/clone-before-upgrade.sql
python -m app.mysql_recovery restore /backups/clone-before-upgrade.sql \
  --sha256 EXPECTED_SHA256 --confirm RESET-typography_fullclone_test \
  --report /backups/clone-restored.json
```

Use new report/backup paths each run. Backup uses database-scoped table locks for MyISAM
consistency; it does not claim recoverability until a restore is tested. Restore
is destructive, verifies the expected source hash first, checks account grants,
then drops/recreates only the clone. SQL imports require trusted source files:
database-scoped credentials provide the actual cross-database safety boundary.

Rollback means restoring the pre-upgrade backup with the previous application
revision stopped from writing. There are no automatic reverse-DDL migrations.
Do not boot a newer image after restore until deciding whether to reapply its
startup migrations. Compare exact row counts/checksums and schema versions with
the pre-upgrade snapshot before declaring recovery successful.

## 3. Production promotion (operator-controlled)

1. Save the current image/commit IDs, environment, MySQL version, and backup.
2. Stop application writers and disable startup jobs during import/restore.
3. Provision a **new** production-candidate database and database-only account.
4. Import the trusted original dump using that restricted account and a protected
   client option file; never grant it global privileges or point clone tools at it.
5. Run the chosen backend image with `DATABASE_URL` set to the candidate, applying
   `python -m app.migrate upgrade`, `python -m app.bootstrap`, and diagnostics.
6. Review historical counts/orphans, reports, permissions, and health before
   switching the application's URL to the candidate. Bootstrap is additive but
   can seed permissions/catalogs; review those changes, not only row counts.
7. Keep the previous database and image untouched for rollback. If cutover fails,
   stop writers, switch back to that pair, and reconcile any post-cutover writes.

The automated clone procedure does not authorize production replacement. Full
restore/upgrade-rollback exercise and target-environment acceptance remain required.