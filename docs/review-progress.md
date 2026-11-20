# Phase 1 review remediation

Phase 2 has not started. Focused Phase 1 tests are not scenario executions.
Scenario report pairs will be initialized at Phase 2 entry as required by scenarios.md.

## Finding register

| Finding | Status | Evidence / next step |
|---|---|---|
| S01 | verified | Domain/lifecycle gates, self-disable and privileged-target restrictions, shared writer serialization, projected last-admin invariant; verified on SQLite and isolated MySQL InnoDB/MyISAM. See completion evidence below. |
| S02 | in progress | Default-disabled registration and pending-account business admission verified locally; 242 backend tests OK (19 MySQL skips), 17 Chromium workflows pass. Disposable MySQL admission verification and pre-rollout account inventory remain; no deployment. |
| S03 | unstarted | Business write authorization across domains and aliases. |
| S04 | unstarted | Role delegation and privileged-target policy. |
| S05 | unstarted | Report domain-read authorization. |
| S06 | unstarted | Bill domain deletion authorization. |
| S07 | unstarted | Password-change remember-token revocation. |
| S08 | unstarted | Logout session revocation. |
| S09 | unstarted | Initialization grant preservation. |
| S10 | unstarted | Actual route authorization coverage. |
| S11 | unstarted | Production launch and strict cookie-authenticated CSRF. |
| S12 | unstarted | Discovery, abuse controls and administrative auditing. |
| F01 | unstarted | Recalculation routing. |
| F02 | unstarted | Sale total and order fields. |
| F03 | unstarted | Blank production inputs and plate automation. |
| F04 | unstarted | Blank unit-price snapshots. |
| F05 | unstarted | Afterprint parameter round trips. |
| F06 | unstarted | Save/recalculate ordering and dirty state. |
| F07 | unstarted | Component activation after adding work. |
| F08 | unstarted | Other-work creation and assigned price. |
| F09 | unstarted | Duplicate payroll assignment and concurrency. |
| F10 | unstarted | Payroll deductions. |
| F11 | unstarted | Calculation snapshot completeness. |
| F12 | unstarted | Economy markup aggregation. |
| F13 | unstarted | Passport production instructions/materials. |
| F14 | unstarted | Payment legal/bank fields. |
| F15 | unstarted | Spreadsheet print settings. |
| F16 | unstarted | Blank mutation errors and lifecycle UI. |
| F17 | unstarted | Imposition/divisor validation. |
| F18 | unstarted | Mutation validation and trash scope. |
| F19 | unstarted | Nested routes and hash destinations. |
| F20 | unstarted | Wide-printer currency propagation. |
| F21 | unstarted | Atomic calculation persistence. |

## S01 first increment — 2026-11-20

Invariant: employee reads require `view_menu_references_users`; deletion requires
`user_delete`; permanent deletion additionally requires `delete_trashed`; restore
additionally requires `restore_trashed`. UI capabilities mirror these gates.

Inspected the archived employee controller, active endpoints, models, frontend
caller and tests. The missing active-delete gate was confirmed in source.
Added real bcrypt/session tests with valid CSRF and before/after snapshots of
every modeled table. All fixture writes use explicitly asserted in-memory SQLite;
TestClient lifespan is not entered, preventing working-database initialization.

Unresolved: target protections and concurrent last-administrator invariants;
MySQL/browser verification; related edit/demotion/matrix paths (S04). Do not claim
S01 fixed or release readiness on the basis of the permission gates alone.

Validation: 7 focused employee tests passed; full backend suite 222 run, OK with
11 opt-in MySQL skips; frontend 19 helper tests passed; production build and both
repository diff checks passed. No Phase 2 scenario was run. No deployment or
shared database was accessed. Changes are limited to the employee boundary.

## S01 self-disable increment — 2026-11-20

Employee delete and update now reject deleting or marking the acting user fired.
A real-session regression checks both denials against snapshots of all modeled
tables and confirms a normal self-edit still succeeds. Eight focused tests passed;
the full backend suite ran 223 tests successfully with 11 MySQL-only skips;
19 frontend helper tests and the production build passed.

Still open: self-demotion, privileged-target handling, and last-effective-admin
protection across user edits and role-matrix updates, including concurrent MySQL
transactions. The current changes do not protect a last administrator from a
different authorized actor and must not be treated as complete S01 remediation.

## S01 privileged-target increment — 2026-11-20

Self-role changes are denied. Employee edit/delete requests targeting a holder
of `view_menu_options_permissions` require that same security-administration
permission. Real-session tests verify denial with all modeled tables unchanged.
Nine focused tests passed; 224 backend tests passed with 11 MySQL-only skips.

Release blocker remains: a security administrator can still disable the last
effective administrator through another account or permission-matrix updates.
The operator-only `app.assign_role` CLI is another role-change path. A shared
transactional lock and effective-admin invariant must cover all three paths and
be tested concurrently on disposable MySQL before S01 can be marked fixed.
General delegation of privileged roles on creation/update remains S04.

## S01 conservative containment — 2026-11-20

Confirmed that the historical dump uses MyISAM; row locks and rollback cannot
be assumed. Added conservative restrictions: administrator accounts cannot
be deleted, fired, or moved to another role through employee APIs or the
operator role-assignment CLI; the permission matrix cannot remove an existing
`view_menu_options_permissions` role grant. This intentionally blocks legitimate
administrative changes until a safe replacement and recovery policy exist.
Real-session tests cover rejected changes and permitted grant retention; CLI
coverage confirms refusal. Full suite: 226 run, OK, 11 MySQL-only skips.

S01 remains open: these checks are not atomic against concurrent assignment or
matrix changes, direct SQL, or other writers; MyISAM rollback is unavailable.
A transactional schema/concurrency strategy and disposable MySQL concurrency
tests are required. No VM deployment or production-like database was changed.

Additional verification: repeated administrator demotion/deletion requests
leave every modeled table unchanged, and operator CLI preview remains read-only.
Eight focused tests and 227 backend tests passed (11 MySQL-only skips). These
checks do not resolve concurrent role-assignment/permission-matrix races.

## S01 completion — 2026-11-20

Supersedes the conservative administrator freeze and concurrency blockers above.
`app/admin_safety.py` serializes employee create/update/delete/restore, matrix
updates, operator role assignment and startup catalog writers. MySQL uses a
database-scoped named lock on a dedicated checked-out connection, held through
commit even for MyISAM; SQLite uses an OS file lock shared across processes.
Timeout/unsupported dialect fails closed. Sessions discard pre-lock snapshots
and refresh identity-map state before checking authorization and proposed changes.

Effective administrator: active, non-fired user whose role contains
`view_menu_options_permissions`; no numeric role-ID or role-title assumptions.
The proposed mutation cannot reduce an existing nonzero administrator population
to zero. Authorized removal of a peer is permitted if another remains. Self-delete,
self-firing and self-role changes remain denied. Non-security staff cannot edit,
delete or restore security-administrator targets. Domain plus lifecycle permissions
are required. Matrix replacement adds grants before removing old grants to avoid
the MyISAM delete-before-insert lockout hazard.

Validation on the post-fix source:
- Full backend: 237 run, OK, 19 opt-in MySQL skips.
- VM isolated MySQL 8.0: 6 real-session tests passed on InnoDB.
- VM isolated MySQL 8.0: 8 tests passed with users/roles/role_permissions confirmed
  MyISAM, including two concurrent demotions and matrix revocation racing an
  operator demotion; exactly one effective administrator remained.
- Frontend: 19 helper tests, 17 Chromium workflows and production build passed.
- Compilation and repository diff checks passed.

VM evidence: `/root/rework/qa-results/s01-authorization/run.log`. QA used a separate
temporary MySQL container/network, tmpfs storage and database-restricted account;
the URL/grant guard ran before fixture writes. No working database credentials
were supplied to the QA containers. Temporary database container/network were
removed. No working container was restarted or application deployment upgraded.

Limits: cooperative application writers only; direct DBA SQL, third-party writers,
manual restores and maintenance must run with application writers stopped. Named
locks are not a general replacement for transactional MyISAM persistence. Recovery
from a historically zero-admin database remains an explicit operator operation.
General role delegation and credential takeover are S04/S07, not silently claimed
resolved here. These are Phase 1 checks, not Phase 2 scenario executions.
## S02 admission boundary — in progress
Public registration defaults off in every environment. Explicit opt-in creates a roleless pending account, never a default manager/admin. A shared FastAPI dependency covers business routes and compatibility aliases; auth, recovery, session, CSRF and health are exempt. Session metadata advertises registration availability and business admission. Frontend hides disabled registration and presents pending approval. Read-only inventory: uv run python -m app.audit_pending_accounts (IDs/state only; no deletion). Existing user schema has no creation timestamp, so this cannot classify accounts by registration date.
Validation: eight focused registration/auth tests passed; frontend 19 helper tests and build passed. Full backend 240 run: 68 failures, 29 errors, 19 skips, primarily legacy roleless mocked fixtures. S02 is NOT complete: reconcile legitimate staff fixtures without overriding admission; run browser pending/disabled-registration tests and disposable MySQL admission tests. Existing S01 real-session regressions must stay green. No working database or VM changed. Phase 2 has not started.

## S02 regression reconciliation

Supersedes the failing-suite status above. Mock-auth CRUD fixtures now explicitly
carry a synthetic admitted role; the admission dependency is never overridden.
Real-session tests separately enumerate every registered business route/method
for guest, roleless and empty-role denial with valid CSRF and unchanged modeled
tables. Opt-in registration remains pending. Approval/revocation takes effect on
subsequent requests; pending accounts can log out. Inventory is read-only.

Browser fixtures distinguish pending accounts from Orders-only staff. Disabled
registration has no form or navigation links. Pending accounts cannot mount
business screens or see business menus; direct API calls still return 403.

Validation: backend 242 run, OK, 19 opt-in MySQL skips, warnings treated as errors;
17 Chromium workflows, 19 frontend helpers, production build, compilation and
diff checks passed. S01 regressions remain green locally. No production/shared
database or VM was accessed. No historical accounts were deleted or reassigned.

Remaining S02 gates: run admission regressions on guarded disposable MySQL;
run the read-only account inventory before rollout and have an operator review
unassigned accounts. Registration date cannot be inferred from the mapped schema.
Per-action permissions/delegation remain S03/S04. Phase 2 has not started.

## S02 disposable MySQL verification completed

Five real-session admission tests passed on a temporary MySQL 8.0 server with
tmpfs data, isolated Docker network and database-restricted credentials. The
database/grant guard ran before fixture writes. Tests cover disabled registration
aliases, opt-in pending registration, guest/roleless/empty-role denial across all
registered business methods, approval/revocation and logout. Denied calls preserve
all modeled tables. Authentication/permission decisions were not mocked.

Evidence: `docs/s02-mysql-results.txt`; opt-in reproduction module:
`tests.test_review_registration_mysql.MySQLRegistrationReviewTests`, enabled by
`S02_MYSQL_URL` pointing to an empty guarded test database. The temporary server
and network were removed after the run. The first attempt failed before test
execution because the source mount was read-only; setting the unused default
SQLite URL to `/tmp` corrected the harness without weakening admission.

Imported only users, roles, permissions and assignments from the original dump
into container-local disposable SQLite, then ran the read-only inventory:
`docs/s02-source-account-inventory.json` reports no pending accounts. This is a
source-dump inventory, NOT an inventory of subsequently registered live accounts.
No working service, database or existing account was changed.

Local full suite: 247 run, OK, 24 MySQL-only skips, warnings treated as errors.
Prior browser evidence: 17 Chromium workflows passed on the same S02 application
code; this step adds tests/evidence only. S02 implementation and disposable
acceptance are complete. Remaining rollout blocker: operator must obtain/review
a fresh read-only live account inventory before enabling this build. Do not delete
or reassign accounts automatically. Phase 2 scenario execution has not started.
