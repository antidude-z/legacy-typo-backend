# S09: initialization preserves imported access

Initialization is serialized with cooperating security writers. A missing
`schema_versions` marker is not evidence of a fresh installation. If any role,
user, permission definition, or role-permission assignment already exists,
initialization adds missing catalog data without granting permissions to roles.
Existing role IDs, permission metadata, assignments (including association IDs),
user credentials and intentionally revoked grants are preserved. Repeating startup
or removing the catalog marker must not restore revoked permissions.

## Fresh baseline

Only an empty access catalog without the current marker receives baseline grants.
New administrator and leadership roles receive the explicit legacy `PERMISSIONS`
catalog (48 definitions), not arbitrary permission rows. The manager receives
`view_menu_orders`, `view_menu_references`, and
`view_menu_references_customers`. Other roles receive no grants. New S03 action
and S04 delegation capabilities are definitions only, not automatic grants.
Initialization never creates a user or assigns a user to a role.

## Read-only approval diff

From the backend checkout:

```sh
uv run python -m app.bootstrap --preview
```

Preview does not create tables or run migrations. It reports fresh/upgrade mode,
existing assignments, proposed additions, no removals, and `applied: false`.
For an existing installation, proposed grant additions must be empty. Preview is
an observation, not a reservation: rerun after concurrent administrative changes.
Capture and review the output before import/upgrade. Any deliberate grant change
requires explicit operator approval through the existing permission administration
workflow; startup does not apply an inferred access migration.

## Initial administrator and recovery

For a new installation, an operator must review the baseline and explicitly
provision an initial account using the existing approved account provisioning
process. Assign the reviewed existing role using `app.assign_role` in preview
mode first, with exact IDs; `--apply` is the separate write confirmation.
No default password or automatic privileged registration is introduced here.
For imported installations without an effective administrator, stop and use the
operator recovery procedure with reviewed IDs and exact grants. Do not rename a
role, remove a version marker, or rerun initialization to manufacture authority.
Direct DBA maintenance requires application writers stopped and a verified backup.

## Validation and rollout

SQLite bootstrap/schema regressions: 18 passed. Full backend: 617 run, OK with
212 opt-in skips. Two explicit tests passed per disposable MySQL engine (InnoDB
and MyISAM), including exact assignment/user preservation, restricted leadership,
empty administrator/manager roles, marker removal after revocation, and fresh
preview/baseline equivalence. Frontend helper suite: 20 passed.

Before release, back up the actual live volumes/configuration, retain rollback
images, capture a fresh read-only preview and exact grant snapshot, deploy, then
compare exact grants and business invariants. Never delete/restore live data to
resolve an unexplained comparison difference. Local validation is not deployment
evidence or Phase 2 scenario acceptance.