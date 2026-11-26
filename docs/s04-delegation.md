# S04 employee delegation boundary

Profile editing (`user_edit`), account creation (`user_create`), role assignment
(`user_assign_role`), credential changes (`user_reset_credentials`) and lifecycle
administration (`user_delete` plus applicable trash permission) are separate.
Creation also requires role assignment: there is no implicit default role.
The two new capabilities are cataloged but never automatically granted.

Non-security administrators may only administer targets whose current effective
grants are a subset of their own, and may only assign roles with subset grants.
Incomparable roles are protected too. Roleless targets have no effective grants.
No numeric role ID, title, ordering or ownership assumption establishes authority.
Holders of `view_menu_options_permissions` are full security administrators and
may cross that subset boundary, but still need each dedicated action capability.
Self-role changes, self-firing and self-deletion remain forbidden; S01's shared
writer lock and last-effective-administrator invariant remain authoritative.

Changing an existing account's email or password requires credential-reset
authority. New-account initial credentials use creation authority. Firing/unfiring
requires employee-delete authority in addition to edit authority. Ordinary profile
edits can retain the existing role without role-assignment authority. All accepted
create/update requests record an Action with actor/target IDs and changed field
names, not values. These records are not an atomic durable auditing guarantee on
historical MyISAM; S12 remains separate. Remember-token revocation is S07.

All checks run in the shared security-writer boundary after session refresh.
Operator-only `app.assign_role` is a trusted local maintenance interface, not an
HTTP delegation endpoint; S01 serialization and last-admin restrictions apply.
Direct SQL and third-party writers must not run concurrently with application
security writers.

## Reproduction

From the backend repository:

```
uv run python -W error -m unittest discover -s tests -q
uv run python -m scripts.s04_mysql_qa
```

The MySQL command creates an owned temporary Docker server with tmpfs data,
random test-only credentials, a database-restricted account and a loopback dynamic
port. URL/grant guards precede writes. It runs the 12 real-session employee cases
on FK-free historical-compatible InnoDB and MyISAM schemas, then removes its
container. It never accepts production credentials or a database URL.

Build `typography-s04-backend` and `typography-s04-frontend` from the repositories,
then run `uv run python -m scripts.s04_browser_qa`. Browser QA uses a private
Docker network, synthetic tmpfs SQLite, read-only source mounts and pinned
Playwright; no host service port or working database volume is supplied.

## Rollout gates

Review and explicitly approve role-assignment/reset grants before rollout; no
existing role is broadened by installation. Back up database, configuration,
checkouts and running-image references before deployment. Preserve working
database/volume mappings and secrets, verify health and read-only service access,
then push the tested revisions. Do not run mutation QA against the deployed
working database. S04 Phase 1 checks do not complete deferred Phase 2 workflows.