# S03 authorization and rollout contract

## Policy

All business callers must first be active admitted staff. S03 retains shared-team
Orders/customer visibility; there is no implicit owner-only restriction. A menu
read grant never implies write authority. `app/s03_policy.py` enumerates the 14
domains and exact read/edit/delete grants. Paper-type reads accept either existing
options/reference read alias; other domains require their own read grant.

- Create/edit/copy/recalculate: domain read AND dedicated edit capability.
- Soft-delete: domain read AND dedicated delete capability.
- Restore: domain read AND domain delete AND `restore_trashed`.
- Permanent deletion: domain read AND domain delete AND `delete_trashed`.
- Deleted-resource reads require `view_trashed`. Nested endpoints require active
  matching parents; trash visibility does not permit editing/copying/recalculating
  deleted resources. Blank permanent deletion requires prior soft deletion.
- Order-scoped choices remain available to authorized Orders readers/editors;
  this does not authorize reference administration. Session filter updates need
  read permission only. Creating a draft is a write, even before explicit Save.

## Deliberate grants, not an automatic migration

Bootstrap catalogs new action permissions without assigning any role, including
administrator or leadership. Existing deployments therefore fail closed until a
security administrator approves grants. Existing role titles/IDs are not a safe
proxy for approval. Do not assign every new permission to every historical writer.

Before rollout, an operator must record the approved role/action matrix, take a
backup, and assign the reviewed grants through the permission-administration UI.
Keep `view_menu_options_permissions` restricted to security administrators. A
read-only role gets only its domain read grant; an editor additionally gets its
domain edit grant; a lifecycle operator additionally gets domain delete and only
the generic trash grants explicitly approved. Review and retain a before/after
matrix. Re-read with the actual staff account and verify a forbidden sibling
domain remains denied. No real role grants were changed by S03 remediation.

This is an outstanding deployment approval, not a missing permissive fallback.
S09 separately tracks historical initialization grant expansion for databases
without the legacy version marker; S03 does not certify that unrelated path.

## Repeatable checks

From the absolute backend checkout, run:

```text
uv run python -W error -m unittest discover -s tests -q
```

`tests/fixtures/s03-routes.json` locks the registered S03 route/method inventory.
`test_review_s03_matrix` exercises every method, alias and dynamic kind with real
sessions and valid CSRF. Domain-specific review modules add valid fixtures,
success, wrong-parent, deleted-parent, lifecycle and unchanged-table checks.
The audit endpoint explicitly reports declared policy, not proof of enforcement.

For an EMPTY disposable MySQL database, set `S03_MYSQL_ENABLED=1`,
`MYSQL_ADMIN_TEST_URL` to guarded database-only credentials, and
`S03_MYSQL_ENGINE=InnoDB` or `MyISAM`, then run:

```text
uv run python -W error -m unittest tests.test_review_s03_mysql -q
```

The URL/grant guard runs before DDL or fixture writes. The harness intentionally
uses the historical FK-free schema and utf8mb3 for MyISAM index compatibility.
It refuses nonempty databases and does not reset any working or restored clone.
Use a dedicated temporary server, never a shared service URL. Setup failures may
leave partial test DDL; inspect/reset only the guarded disposable database.

Browser checks use synthetic `data/browser-e2e.db`, never the working service.
The standard frontend Playwright command remains available. On this Windows host
Playwright 1.65.1 completes assertions but can hang at shutdown, even on Node 26.
`scripts.browser_local_qa` owns/checks/cleans local servers but does not claim to
repair Playwright worker shutdown. A clean full run was obtained in an isolated
Linux Playwright 1.65.1 container with Node 26; see review-progress.md for counts.

Phase 1 authorization checks are not Phase 2 scenario runs or production cutover
approval. S04–S12 and functional blockers remain separate release gates.