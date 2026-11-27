# Phase 1 review remediation

Phase 2 has not started. Focused Phase 1 tests are not scenario executions.
Scenario report pairs will be initialized at Phase 2 entry as required by scenarios.md.

## Finding register

| Finding | Status | Evidence / next step |
|---|---|---|
| S01 | verified | Domain/lifecycle gates, self-disable and privileged-target restrictions, shared writer serialization, projected last-admin invariant; verified on SQLite and isolated MySQL InnoDB/MyISAM. See completion evidence below. |
| S02 | in progress | Default-disabled registration and pending-account business admission verified locally; 242 backend tests OK (19 MySQL skips), 17 Chromium workflows pass. Disposable MySQL admission verification and pre-rollout account inventory remain; no deployment. |
| S03 | fixed | Phase 1 implementation and local SQLite/MySQL InnoDB/MyISAM/browser acceptance complete. Production role-grant approval and Phase 2 scenarios are separate pending rollout gates; see completion evidence below. |
| S04 | fixed | Phase 1 SQLite/MySQL/browser acceptance passed; backed up and deployed on 2026-11-26 with unchanged business checksums and role grants. Phase 2 remains deferred. |
| S05 | fixed | Phase 1 SQLite/MySQL/browser validation passed; deployed 2026-11-26 with unchanged business checksums, grants and pending accounts against a fresh baseline including the developer-created bill. |
| S06 | fixed | Explicit bill/payment domain-delete and lifecycle conjunction; 597 backend tests OK (204 skips), 4 tests per MySQL engine and 23 browser workflows pass. Backed up/deployed 2026-11-26 with unchanged business checksums and role grants. |
| S07 | fixed | Shared credential revocation/security stamp, lifecycle and recovery policy verified; 607 backend tests OK (209 skips), 6 S07 cases per MySQL engine and 24 browser workflows passed. Schema-aware rollout completed 2026-11-26 with preserved user values/business data/grants. |
| S08 | fixed | Logout rotates the account security stamp under the serialized security writer, clears remember credentials and the local session, and expires the remember cookie. Copied signed session and remember cookies are rejected after logout. Deployed and independently verified 2026-11-26. |

## S08 deployment — 2026-11-26

S08 was packaged from the pushed backend/frontend commits into
`s08-source.tar.gz`, SHA-256
`c8ba4389bfe1bdc8fa2cfd1af3fadea8e6efa3ebf3e615c4c379d2de886ce153`, and
verified remotely before image builds. A fresh live backup was captured at the
path recorded in `/root/backups/s08-latest-path`; database, checkout/config and
backend-data archives passed gzip/tar and SHA256SUMS checks. The backup health
probe saw transient 502 responses while services restarted, but subsequent
read-only inspection confirmed the pre-deploy S07 services healthy and all
health/session/root endpoints returned 200.

Candidate images `s08-candidate-backend` and `s08-candidate-frontend` built
successfully. The additive migration command applied successfully with stdin
closed; deployment recreated only backend/frontend under the MySQL profile.
`rework_mysql_data` remained mounted and MySQL was not recreated. Independent
verification returned `S08_VERIFY_OK` / `SSH_EXIT=0`: all services healthy,
source hashes matched the candidate, pre/post user/business/grant invariants
matched, the rollback image remained available, and the guest employee route
returned 401. No business data mutation was performed.

VM checkout synchronization returned `S08_SYNC_OK` / `SSH_EXIT=0` at backend
`55eab8c4cf064b0474e719fc5d1ddbbb371c0b7d` and frontend
`aea6954083dcd1b16f519a6540919600deeb9969`. Both remote checkouts were clean.
| S09 | fixed | Initialization preserves imported role grants and users when the schema marker is missing; fresh baseline seeding is explicit and previewable. SQLite/InnoDB/MyISAM acceptance, backup, deployment, independent verification, publication, and VM synchronization completed 2026-11-26; see docs/s09-initialization.md. |

## S09 deployment — 2026-11-26

Packaged and remotely verified source archive SHA-256:
`2206e5917f5b0789d087529632573e1fd0d9082f8d18a6bfb9cac2c5aabf669f`.
Fresh backup: `/root/backups/s09-20261126T145626Z`; database, checkout/config,
and backend-data archives passed integrity and SHA256SUMS checks. The backup
restart probe briefly observed services in health-starting/502 state; follow-up
read-only inspection confirmed S08 backend/frontend/MySQL healthy before rollout.

S09 candidate images built and deployed under the MySQL profile. No migration or
business-data write was performed; only backend/frontend were recreated and
`rework_mysql_data` was retained. The live candidate preview reported `mode:
upgrade` with zero grant additions and zero removals. Pre/post exact user-column
digests (including `security_stamp`), business counts/checksums, and role grants
matched; the accountant payer-edit grant remained present. Candidate services,
MySQL volume, rollback image, source hashes, and guest employee 401 passed
independent verification: `S09_VERIFY_OK`, `SSH_EXIT=0`.

Published backend commit: `2d70291931d25a848a84677e96164d22a3298705`.
Frontend remained at published `aea6954083dcd1b16f519a6540919600deeb9969`.
Final VM checkout synchronization returned `S09_SYNC_OK`, `SSH_EXIT=0`; both
checkouts are clean. This is Phase 1 evidence, not Phase 2 scenario acceptance.
| S10 | fixed | Exact route/policy inventory, real-session grant/revocation coverage and reader-safe payroll. Deployed and independently verified 2026-11-26 UTC after fixing a historical rate-seed precision blocker; all-table/user/grant invariants preserved on retry. 635 backend tests OK (219 skips), 6 S10 and 3 bootstrap tests per MySQL engine, 21 frontend helpers and 25 browser workflows passed. Phase 2 deferred. See docs/s10-authorization-audit.md. |
| S11 | in progress | Cookie-CSRF containment backed up, deployed, independently verified and synchronized 2026-11-26 with unchanged all-table/user/grant invariants. 646 backend tests OK (221 skips), 28 targeted tests, 2 tests per MySQL engine, 21 frontend helpers and 25 browser workflows passed. Production overlay validated but not activated: verified TLS origin/certificate/proxy remains the blocker; HTTP validation access retained. See docs/s11-production-csrf.md. |
| S12 | verified | Discovery, persistent abuse controls, generic registration/recovery responses and durable administrative audit are implemented. Final rollout verification and synchronization evidence is appended below; TLS remains the separate S11 blocker. |
| F01 | verified | Specific bodyless order recalculation route is registered before the generic `{operation}` route; exact browser-shaped POST and generic-operation payload regression pass. Complete Phase 1 backend/frontend/build validation passed; deployment and Phase 2 scenario evidence are recorded separately below. |
| F02 | fixed | Backend and both order forms now preserve negotiated sale total, book volume, and wide width/height with derived format/area. Localized decimal input is parsed server-side and recalculation continues to preserve sale total. Focused backend and frontend contract regressions pass; end-to-end browser acceptance and deployment remain pending. |
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

## F02 order fields — 2026-11-27

The order API now accepts sale total, book volume, and wide width/height on the
create, update, and copy paths. Sale total and dimensions use a shared finite
decimal parser that accepts the legacy localized form (`12 345,67`) and returns
422 before mutation for invalid values. Wide orders derive `format` and `volume`
from the stored dimensions; calculation continues to use the negotiated sale
total as `stored_total` rather than replacing it with production cost.

`OrderForm.svelte` now exposes sale total for every new/copy order, book volume,
and wide dimensions. `OrderDetail.svelte` exposes sale total and volume plus
wide dimensions and submits them through the existing save contract.

Validation on disposable/local fixtures:

- Backend F02/order-authorization focused suite: **35 tests passed**.
- Frontend helper/contract suite: **22 tests passed**, including the new F02
  form-field/API contract test.
- Frontend production build: **passed**, Vite 6.4.5, 159 modules transformed.
- Complete backend discovery was launched but repeatedly stalled in the existing
  audit-heavy tests before a summary; it was terminated locally and is not
  claimed as a full-suite pass.
- No working or deployed database was accessed, and no browser scenario or
  deployment is claimed for F02 yet.

## F01 recalculation routing — 2026-11-27

The review defect was reproduced from the actual frontend caller:
`Calculation.svelte` sends `POST /api/orders/{id}/recalculate` with no request body.
The generic `POST /api/orders/{order_id}/{operation}` route previously appeared
first and required `payload: dict`, so FastAPI returned 422 before the dispatcher
could call the specific recalculation handler.

The specific `/api/orders/{order_id}/recalculate` route now precedes the generic
operation route. No `{}` workaround was added, and the generic operation contract
remains unchanged for other operation names.

Permanent real-session SQLite regressions in
`tests/test_review_order_authorization.py` use a valid session, CSRF header, real
order fixture and actual TestClient routing:

- bodyless browser-shaped recalculation returns 200 and includes `result` and
  `stored_total` calculation fields;
- bodyless non-recalculation operation creation still returns 422 because its
  payload is required.

Focused F01 pair: **2 tests passed in 1.025s**. The complete backend suite then
passed **693 tests with 247 opt-in skips** under warnings-as-errors. Frontend helper
tests passed **21**, and the locked-dependency frontend production Docker build
completed successfully. No working or deployed database was used by these tests.
F01 is verified for Phase 1; Phase 2 scenario execution remains deferred. The
deployment and remote synchronization evidence for this increment follows below.

## F01 deployment — guarded rollout and audit-store correction

The first guarded rollout reached healthy candidate services and passed route,
CSRF, discovery and abuse verification. Independent verification then found that
`SECURITY_AUDIT_DB=/app/data/security-audit.db` was configured but the file did
not yet exist because the audit journal was initialized lazily only on the first
covered event. The production probe's method-boundary 405 did not create such an
event. This was corrected by initializing the protected audit SQLite store during
application startup, with a permanent initialization regression. No business
data, grants, TLS/HTTP setting or MySQL volume was changed by the failed verify.

Focused correction checks: **2 tests passed** (audit initialization and F01
bodyless route dispatch). The corrected revision must be repackaged and pass the
backup, candidate-build, invariant, audit-file, health and synchronization gates
before deployment is marked complete.

## S12/F01 final verification correction — 2026-11-27

The independent verifier initially reached route, CSRF, discovery and abuse checks
but could not find the audit journal because its anonymous probe used a GET request
and admission-denial auditing covered only mutating methods. Admission denials for
the protected employee/matrix read boundary now produce durable `denied` events as
well. A permanent regression verifies a guest employee-read denial creates an
allowlisted audit event; audit-store startup initialization and bodyless F01 route
dispatch also pass. The corrected source is backend `6dad01d` and frontend
`9811b9f`, both published.
Final corrected rollout completed with `S12B_DEPLOYMENT_OK`, `S12B_VERIFY_OK`
and `S12B_SYNC_OK`, all SSH exit 0. Fresh backup:
`/root/backups/s12b-20261127T100318Z`; database, checkout/config and backend-data
archives passed integrity checks. Candidate backend/frontend images built and all
services are healthy. Independent verification passed 179-route inventory, CSRF,
discovery, abuse-enforcement, durable-audit-denial, exact user/business/grant
invariants and retained `rework_mysql_data`. VM checkouts synchronized cleanly to
backend `8bcee48ddd81ba7b5b3016ac940fdb11d214ec5c` and frontend
`9811b9ff678df183aa2d73a8bc6d6406c39d62d2`. HTTP/8080 and TLS settings remain
intentionally unchanged; S11 TLS activation is still separate.
are intentionally unchanged.

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

## S03 Orders action boundary — in progress

Added dedicated `edit_orders` and `delete_orders` capabilities to the catalog,
without granting either to existing roles (including administrator). Operators
must approve assignments before rollout. Orders reads require `view_menu_orders`;
create/edit/copy/recalculate require that read grant plus `edit_orders`;
delete/restore require the read grant plus `delete_orders`. Explicit restore and
permanent-delete paths additionally require their generic lifecycle grant. The
shared dependency covers Orders aliases and nested operation/blank endpoints.
Session-only filter mutations remain read-authorized. Shared-team visibility is
retained; no owner-only policy was invented.

Real-session disposable SQLite regressions prove valid existing-resource reads,
denial without database changes for seven mutation paths, editor success without
delete authority, and rejection of unrelated admitted staff on read aliases.
Full backend: 255 run, OK, 24 opt-in MySQL skips, warnings treated as errors.

S03 remains a release blocker: payer and all reference-family action policies;
deleted-parent/cross-parent/lifecycle matrices and implicit permanent-delete
paths; narrowly scoped selectors; frontend capabilities; deliberate approved-role
grant migration; guarded MySQL and browser verification. No deployed service or
working database changed. Phase 2 has not started.

## S03 payer action boundary — verified local slice

All payer routes now require `view_menu_accounting_payers`. Form preparation,
create and update also require `edit_accounting_payers`; delete and restore
require `delete_accounting_payers`. Restore/permanent delete additionally require
the corresponding generic lifecycle permission. Checks precede resource lookup
and writes. New capabilities are cataloged but not granted to existing roles.
Bill selectors retain their separate bill-scoped contract; no payer catalog
administration access is conferred by an Orders or Bills menu grant.

Responses expose can_edit/can_delete and composed lifecycle capabilities. The
payer frontend hides unauthorized creation/deletion and makes reader fields
read-only. Direct URLs remain protected by the API, not just hidden controls.

Real-session disposable SQLite tests cover unrelated staff, read-only, writer,
generic-trash-without-domain-delete and authorized lifecycle success, with
all-modeled-table snapshots on denials. Targeted suite: 11 passed (including
inherited employee regressions). Full backend: 263 run, OK, 24 MySQL skips,
warnings treated as errors. Frontend: 19 helpers and production build passed.

Remaining S03 blockers: reference-family read/write/delete policies, Orders
implicit-permanent-delete/deleted-parent coverage, approved grant rollout,
frontend Orders/reference alignment and real browser/MySQL verification. This
slice is not a completed S03 acceptance matrix. No VM or working data changed.

## S03 customer administration — verified local slice

All customer administration endpoints require `view_menu_references_customers`.
Form preparation/create/update additionally require `edit_reference_customers`;
delete/restore require `delete_reference_customers`, with restore/permanent-delete
also requiring the corresponding generic trash grant. New capabilities are
cataloged without assigning them to any existing role. Checks precede row lookup
and mutation. Existing shared-team visibility is retained; owner/team scoping
has not been invented. Order-scoped metadata continues to supply customer choices
without exposing full customer administration to Orders-only staff.

Frontend fields/actions consume composed can_edit/can_delete/lifecycle flags.
Real-session disposable SQLite tests cover unrelated admitted staff, readers,
writers, trash grants without domain-delete authority and successful lifecycle
actions on existing records. Denials preserve every modeled table.

Validation: 16 targeted tests passed (including inherited S01 regressions);
full backend 279 run, OK, 24 opt-in MySQL skips, warnings treated as errors;
19 frontend helper tests and production build passed. Browser/MySQL validation
of this slice is still pending. No VM, working database or deployment changed.
S03 remains OPEN: inventory and production-reference action policies, remaining
Orders lifecycle/deleted-parent/cross-parent checks, frontend alignment, approved
grant assignments and complete post-fix disposable browser/MySQL matrices.

## S03 paper/material inventory — verified local slice

Inventory administration requires the matching `view_menu_references_paper` or
`view_menu_references_materials` read grant. Each has dedicated
`edit_reference_<kind>` and `delete_reference_<kind>` capabilities; catalog
initialization does not grant them to existing roles. Draft/create/update require
edit; delete/restore require delete plus existing lifecycle gates where applicable.
Material session filtering requires read only. Generic form/detail/list paths
use the same inventory boundary. Order-production metadata remains separate.

API responses supply composed capabilities; frontend readers have disabled
editing fields and no create/delete actions. Material creation consumes the
form-options capabilities so authorized writers can still submit.

Real-session disposable SQLite covers both kinds, valid records, denied reads
and writes, all-table snapshots on denial, editor create/update success, filters,
generic-trash-without-domain-delete denial, restore and permanent-delete success.
Full backend 286 run, OK, 24 MySQL skips with warnings treated as errors; targeted
inventory/bootstrap suite 15 passed; final focused suite 7 passed; frontend 19
helpers and production build passed. No VM or working database changed.

S03 remains OPEN: printer/field/process/stage, afterprint, compilation and work
catalog policies; Orders lifecycle/deleted-parent/cross-parent gaps; approved grant
rollout; frontend alignment and full browser/MySQL acceptance. These fixes are
not deployed and Phase 2 workflow execution has not started.

## S03 printer production hierarchy — verified local slice

Printer definitions, fields, processes and stages share a domain boundary:
`view_menu_references_printers` for reads, plus `edit_reference_printers` for
draft/create/update, or `delete_reference_printers` for delete/restore. Restore
and permanent deletion still require their separate generic lifecycle grant.
The two new capabilities are cataloged without automatic role assignment.
Authorization runs before resource lookup; existing printer/process ownership
checks and deleted-parent rejection remain enforced. No calculation formulas or
order-production selector contracts changed.

Frontend parent/child lists, forms and confirmations consume composed capability
flags. Readers retain navigation but cannot edit, create or trigger lifecycle
actions. Backend remains authoritative for direct requests.

Real-session disposable SQLite tests cover valid parent/child resources, reader
write denial, writer success, generic-trash-only denial, domain-delete without
generic lifecycle denial, permitted restore/permanent deletion, wrong printer or
process ownership, and deleted printer/process rejection. Rejected calls compare
all modeled tables for unchanged state.

Validation: initial targeted suite 31 passed; expanded focused suite 9 passed
(including inherited S01 checks); full backend 295 run, OK, 24 opt-in MySQL skips,
warnings treated as errors; 19 frontend helpers and final production build passed.
An intermediate Svelte closing-block error was caught and corrected before commit.
No VM, working database or deployed service changed.

S03 remains OPEN: afterprint/compilation/work-catalog action policies, remaining
Orders lifecycle/parent gaps, approved role assignment rollout, policy-manifest
reconciliation, and complete post-fix browser/disposable MySQL acceptance. Phase 2
scenario execution has not started.

## S03 dictionary action boundaries — verified local slice

Paper types, paper formats, measures and customer groups now require their
existing dictionary read grant. Paper types accept either existing options or
references read alias. Each dictionary has distinct `edit_dictionary_<kind>` and
`delete_dictionary_<kind>` capabilities (hyphens replaced with underscores).
These eight capabilities are cataloged but never assigned automatically.
Draft creation, store and patch require edit; delete/restore require delete;
generic trash permissions remain additional requirements, not substitutes.
Unrelated dictionary writers gain no access. Order metadata selectors are
unchanged and do not require dictionary-administration grants.

Frontend create, edit, delete and lifecycle controls consume composed backend
capabilities; read-only fields are disabled. API checks remain authoritative.
Real-session disposable SQLite matrix covers all four dictionaries, valid rows,
draft denial, store/patch/delete/restore denial, writer success, lifecycle success,
cross-dictionary denial and unchanged modeled tables on rejected requests.

Validation: targeted 19 tests passed; full backend 271 run, OK, 24 opt-in MySQL
skips with warnings treated as errors; 19 frontend helpers and build passed.
No VM, working database or deployed service changed. S03 remains OPEN for
customers/inventory/production reference families, Orders lifecycle and parent
checks, approved grant rollout and post-fix browser/MySQL acceptance.

## S03 afterprint hierarchy — verified local slice

Definition reads and nested forms require view_menu_references_afterprints.
Definition edits and stage/material creates/updates additionally require
edit_reference_afterprints; child delete/restore require
delete_reference_afterprints plus the applicable generic lifecycle permission.
New grants are cataloged, not automatically assigned. Frontend controls follow
composed backend capabilities. Deleted definitions reject child access/mutations;
deleted stages reject material access/mutations even with view_trashed.

Real-session disposable SQLite tests cover reader/writer/lifecycle combinations,
unrelated staff, wrong definition/stage ownership, deleted parents and unchanged
modeled tables after denial. Full suite before the final added lifecycle test:
303 run, OK, 24 MySQL skips; final focused suite: 9 passed. Frontend 19 helper
tests, build and diff checks passed. No working database or deployment changed.
S03 remains open for compilation/work catalogs, Orders edge cases, grant rollout,
policy manifest and browser/MySQL acceptance. Phase 2 has not started.

## S03 compilation hierarchy — verified local slice

Compilation definitions, stages and stage-material assignments now require
view_menu_references_compiles for reads; edit_reference_compiles for create/edit;
delete_reference_compiles for delete/restore plus the applicable trash grant.
Capabilities are seeded without automatically assigning roles. Child operations
reject deleted definitions; material operations reject deleted stages, even for
view_trashed holders. Existing parent ownership checks remain enforced.
Frontend create/edit/delete actions consume composed backend capabilities.

Real-session disposable SQLite tests cover unrelated staff, readers, writers,
domain/generic lifecycle combinations, successful mutations, wrong ownership,
deleted parents and all-modeled-table snapshots after denial. The first copied
fixture cleared a production flag during definition editing; the fixture now
explicitly retains that flag before testing compatible material writes.

Full backend: 313 run, OK, 24 opt-in MySQL skips with warnings as errors. Frontend
19 helper tests and build pass. No deployment/database changes. S03 remains OPEN:
prepress/redaction work catalogs, Orders lifecycle/deleted-parent/ownership edges,
approved role grants, policy manifest reconciliation and browser/MySQL acceptance.

## S03 prepress/redaction catalogs — verified local API slice

Inspected both archived catalog controllers, active models, API handlers, frontend
caller and existing tests. Real-session regressions reproduced unrelated staff
reading catalog rows and a revoked writer still creating rows (HTTP 200).

Both catalog families now require their own `view_menu_references_<kind>` grant.
Create/update and creation form options additionally require
`edit_reference_<kind>`; delete/restore require `delete_reference_<kind>`.
Restore and permanent deletion additionally require the corresponding generic
lifecycle grant. Prepress permissions do not authorize redaction administration.
Four capabilities are cataloged idempotently without assigning existing roles.
Order-scoped selectors and calculation behavior are unchanged.

Frontend creation fetches authorized form options; list/edit/delete controls use
backend capabilities. Readers can inspect disabled forms but cannot save or delete.
Real-session SQLite tests check both families, revoked grants, invalid/missing and
deleted rows, repeated restore, successful writes/lifecycle, generic-only and
domain-only lifecycle denial, and unchanged snapshots of every modeled table.

Validation: focused API/bootstrap suite 17 passed; full backend 323 run, OK with
24 opt-in MySQL skips, warnings treated as errors; frontend 19 helpers and build
passed. New Chromium reader/writer test completed all assertions (1 passed), but
the runner timed out during teardown at 120 seconds and exited nonzero: this is
NOT a clean browser-suite pass. Earlier attempts encountered a browser launch
hang and an overly strict test URL assertion; the latter now permits the existing
pagination query string. Local Node is 25.2.1, not the documented Node 26.
The catalog-reader login also exposes an existing Orders screen error on its
forbidden landing route (`Cannot read properties of undefined (reading 'page')`);
that frontend admission/error-handling edge remains to be addressed.

S03 remains OPEN for Orders lifecycle/deleted-parent/ownership edges, manifest
reconciliation, operator-approved grants and guarded MySQL/full browser acceptance.
No VM, working database or deployed service changed. Phase 2 has not started;
scenarios.md was not read or executed.

## S03 Orders resource/trash boundary — local regression increment

Pushed preceding backend 24230fe (fix/mysql-runtime) and frontend 5071bda (main)
to GitHub; remote branch hashes verified. No VM pull/rebuild or deployment.

Inspected archived Blank/OrderPrepress lifecycle behavior, current route dispatch,
models, operation/calculation tests and frontend consumers. Real-session SQLite
tests reproduced four gaps: deleted-parent updates, deleted-child updates,
permanent deletion of active blanks, and repeated unauthorized deletes returning
200 while changing tombstone timestamps.

The shared business dependency now applies Orders resource scope before handlers:
missing/orphan/cross-parent children return 404; nested access requires an active
parent; deleted orders are read/history-visible only with view_trashed and reject
ordinary edits/copy/recalculation. Deleted children reject update/copy/recalculation;
detail requires view_trashed. Restore remains domain-delete plus restore_trashed;
implicit and explicit permanent deletion require domain-delete plus delete_trashed.
Active blank permanent-delete requests return 409 (soft-delete first). Repeated
blank DELETE now follows the same guarded permanent-delete policy as operations.
No owner-only restriction was added: shared-team visibility remains intentional.

Composed edit/delete/restore/permanent-delete capabilities are returned by Orders
list/detail/operations. Main form, calculation, list creation and operation controls
consume them. Failed order deletion no longer navigates away as if successful.
The catalog-only reader's forbidden Orders landing page now shows an access-denied
alert without replacing list data with an error payload or crashing pagination.

Validation before the final added revocation test: full backend 330 run, OK with
24 opt-in MySQL skips, warnings as errors; frontend 19 helper tests/build passed.
Both new Chromium tests completed assertions (catalog writer/reader and Orders
reader); runner again timed out during teardown at 120s, nonzero exit. This is
NOT a clean browser-suite pass. Follow-up test/suite results are appended below.

S03 remains OPEN: blank editor/create/copy UI capability alignment, complete route
matrix/policy-manifest reconciliation, deliberate approved role grants, guarded
MySQL acceptance and clean full browser validation. Historical data, calculation
formulas and deployed/working databases were not changed. Phase 2 not started.

Final validation including revoked-edit and all-child reader checks: 331 backend
tests run, OK, 24 MySQL skips; backend/frontend diff checks and browser-test syntax
check passed. The new tests compare every modeled table after each rejected call.

## S03 Phase 1 completion — 2026-11-20

Supersedes the remaining implementation/acceptance gaps in the earlier increments.
The finding is FIXED for Phase 1, not marked fully VERIFIED under the review's
scenario-based definition of done: scenarios.md remains deferred at user request.

Completed blank/create/copy frontend capabilities, disabled reader markups,
blank trash listing/restore/permanent-delete controls, and order restore controls.
Creation metadata requires edit authority; format suggestions remain read-scoped.
Deleted rows cannot be edited/copied/recalculated. Existing shared-team visibility
and narrowly scoped order selectors remain available without reference-admin rights.

The checked inventory contains 127 registered route/method pairs across all S03
families. The real-session matrix expands dynamic dictionary/inventory/work and
order-operation kinds, verifies denial for unrelated/reader/wrong-domain/generic
lifecycle/editor combinations, and checks every modeled table after denial.
Existing domain suites verify successful legitimate mutations, lifecycle conjunctions,
missing/deleted/wrong parents, revocation, and valid resource reads. S02's separate
all-business-route tests retain guest/roleless/empty-role coverage.

The audit payload now accurately declares S03 policy, includes every dedicated S03
action grant in catalog checks, and explicitly says catalog completeness is NOT
enforcement certification. `docs/s03-authorization.md` defines policy, repeatable
checks and deliberate rollout. Bootstrap tests prove all 28 new domain-action
capabilities are cataloged without automatic role assignments and approved grants
survive repeat initialization. No grant migration based on role title was invented.

Final validation:
- Backend: 432 tests run, OK, 116 opt-in skips (including 92 new MySQL cases),
  warnings treated as errors. An earlier run exposed an intermittent pre-existing
  Windows S01 file-lock initialization PermissionError; unchanged rerun passed.
  This was not hidden by modifying unrelated S01 code.
- Dedicated temporary MySQL 8.0: 92 tests passed on InnoDB and 92 on MyISAM,
  no skips, final runs include the updated blank visibility/revocation assertions.
  URL/database-only grant checks run before fixture writes. Historical FK-free
  schema used; first MyISAM setup failed on utf8mb4 key length before tests;
  harness now uses legacy-compatible utf8mb3. Partial test-only DDL was reset.
- Frontend: 19 helper tests and production build passed.
- Full Chromium: 20 passed, zero skips/failures/flakes/runner errors, exit 0,
  37.34 seconds in isolated Playwright 1.65.1 Linux container on Node 26.13.1.
  Includes read-only Orders/blank/create/copy controls, catalog readers/writers,
  and authorized blank soft-delete/restore/permanent-delete. An older reference
  workflow assertion was corrected to accept the existing pagination query string.
- Windows Playwright assertions also passed but runner shutdown still hangs on
  both Node 25 and 26, even with externally managed servers. The clean Linux run
  is the acceptance evidence; the bounded local harness cleans its owned servers.

No production-like database or deployed service was mutated; all MySQL writes
were to the temporary local test container, and browser writes to synthetic
SQLite in temporary QA containers. Temporary containers/network are removed after
verification. No physical-print/business acceptance or Phase 2 run is claimed.

Remaining deployment decisions (not permission bypasses): security administrator
must approve/assign actual staff role grants before rollout; no real role was
broadened. S09 separately tracks initialization on historical databases without
the version marker.
S04–S12 and F01–F21 remain their own release blockers.

## S04 local implementation increment — 2026-11-26

Inspected the archived employee controller, current models, API, frontend and
real-session employee regressions. Added separate user_assign_role and
user_reset_credentials gates, cataloged additively without automatic role grants.
Role delegation and target management compare effective permission sets, not
role titles/IDs. Only security administrators bypass the subset boundary; domain
and sensitive-action gates still apply. Self-role changes remain forbidden.
Firing/unfiring additionally requires user_delete. Unchanged roles remain valid
for profile-only edits. Create requires a deliberately selected assignable role;
the browser no longer selects the first database row. UI sensitive fields consume
capabilities, and role choices are filtered server-side. Employee create/update
adds Action records containing IDs and changed field names only, never secrets.

Validation before the final audit-record addition: 10 focused real-session SQLite
tests passed with 10 MySQL skips; 5 bootstrap tests passed. Docker node:26-alpine
ran npm ci, all 19 frontend helper tests and production build successfully.
Full backend: 476 run, 138 opt-in skips, two deployment-test errors caused by
hard-coded workspace backend/frontend names versus this checkout's
legacy-typo-backend/legacy-typo-frontend names. No other failures reported.
After the audit-record addition: 10 real-session SQLite checks passed with 10
MySQL skips; all 6 bootstrap checks passed. The audit-content assertions added
after that run still require final confirmation below.

S04 remains IN PROGRESS: expanded role/alias/revocation and audit regressions,
disposable MySQL/browser acceptance and deployment compatibility review remain.
S07 credential revocation and S12 broader durable auditing are separate blockers;
do not treat Action records as an atomic MyISAM audit guarantee. No scenarios
were intentionally opened/executed; an earlier unscoped search inadvertently
returned snippets, so subsequent inspection uses explicit file paths.

User requires every completed safety/functional fix to be backed up and deployed
to the service server, health-checked, then pushed to Git. No backup, transfer,
deployment or push has occurred for this incomplete increment. No working
database was used for mutation tests. Server authentication details are absent
from the resumed context and must be recovered securely before rollout.

## S04 expanded acceptance increment — 2026-11-26

Added explicit role-choice/creation/legacy-payload/revocation checks and verified
that security administrators still require credential-reset authority. Twelve
real-session cases passed on isolated MySQL 8.0 InnoDB and twelve on MyISAM,
with no skips. The disposable Docker server used tmpfs storage, random credentials,
loopback dynamic port and database-only grants; the URL/grant guard ran before
writes and the owned container was removed. Reproduction: scripts/s04_mysql_qa.py.

Both backend and frontend Docker images built successfully. Fixed deployment-test
path discovery for the renamed checkout repositories; all four deployment checks
pass. Full backend: 565 run, OK with 182 opt-in skips, warnings treated as errors.
That run double-counted imported MySQL fixture classes; imports were changed to
module aliases and a fresh full run is pending for the corrected test count.

Added the S04 browser workflow and a synthetic profile-editor fixture. The owned
Docker browser harness uses read-only source mounts, private network and tmpfs
SQLite; no working volumes or host service ports. Playwright image download is
still in progress: no browser pass is claimed. Both repository diff checks pass.
Policy/rollout contract is docs/s04-delegation.md. Deployment and Git push have
not occurred. S04 remains in progress pending browser/final checks and rollout.

## S04 final local acceptance — 2026-11-26

Supersedes the pending local validation notes above:

- Full backend: 577 tests run, OK, 194 opt-in skips, warnings treated as errors.
- Guarded disposable MySQL: 12 S04 cases passed on InnoDB and 12 on MyISAM,
  no skips in those explicit runs.
- Frontend helper suite: 19 passed. Both application Docker images built.
- Full isolated Chromium: 21 passed in 34.8 seconds, no skips or failures.
  The first run skipped the historical orphan workflow because the existing
  remote-URL guard hid it. The owned synthetic harness now explicitly advertises
  its disposable orphan fixture; rerun included and passed that workflow.
- Compilation reported no errors; both repository diff checks were clean.
- Final Docker container inventory is empty; owned MySQL/browser containers
  were removed. Source diff and all added QA scripts/tests were inspected.

S04 remains IN PROGRESS under the user's required completion sequence: server
backup, code transfer, deployment, read-only service health verification, then
Git push are not done. Resumed context lacks server authentication details; ask
for the SSH endpoint/user and secure authentication method, without recording
credentials in this document. Actual sensitive-action role grants also require
explicit operator approval; installation does not broaden any existing role.
Do not deploy by guessing database/volume mappings or silently granting roles.

Phase 2 remains deferred. S05–S12 and all functional findings remain open; these
test results do not establish full migration readiness. No working service or
business database has been mutated during this S04 local acceptance.

### S04 rollout access restored; terminal execution blocked

The user supplied the VM SSH endpoint and authentication again. Credentials are
not recorded here. Deployment remains authorized in the required order: verified
backup, code transfer, deployment, service health checks, then Git push.
Two initial local command attempts failed before execution with the terminal-tool
error "The terminal's shell process has exited; the command was not run."
No SSH connection, backup, transfer, deployment or push occurred. File reads still
work. Re-read deployment overlay/runbook confirms the documented working database
typography_restored and external volume rework_mysql_validation; actual VM state
must still be inspected read-only before any rollout action. Restore terminal
execution first, then resume backup and deployment without guessing live mappings.

## S04 deployment — 2026-11-26

Supersedes previous terminal/access blockers. SSH authenticated against the existing
trusted host key. Read-only inspection found healthy containers and clean VM
checkouts at backend 0ba5bb5/frontend 1010dd6. Crucially, live MySQL uses volume
rework_mysql_data, not the older documented rework_mysql_validation. Preserved
the actual Compose pair, project name, database typography_restored, secrets,
backend-data volume and frontend port 8080. One active pending account (ID 28)
was inventoried without reassignment or deletion.

Rollback backup: /root/backups/s04-20261126T091852Z. Contains locked MySQL dump
(54 MyISAM and 2 InnoDB tables), checkout/config archive, backend-data archive,
container metadata, revisions and SHA256SUMS. Application writers were stopped
for the database/data capture and restarted. All three archive checksums and
compression/archive checks passed. Previous image references remain tagged;
rollback-images.yaml is in the backup. This is integrity verification, not a
completed restore rehearsal or off-host backup.

Transferred source-only archive SHA256
e8fc49a71e10e8b2d8bf0865c652eec1d187fafde9c926bcf9819f774876001d,
verified remotely and built backend/frontend candidates on the VM. Candidate
backend image: 5ca03eb24e41067b4533622d99740554c612ff705d4270416b66a8cfb6891462;
frontend: 02538193dbf66a6432ec9bc68be8d586db2f66413727b68b264b67d78235c0d1.
Compose profile mysql is required even for configuration inspection; an initial
inspection omitted it and failed without changing running containers.

Deployed only backend/frontend with --no-deps --no-build and health-gated wait;
MySQL was not recreated. Live override: /root/backups/s04-candidate-images.yaml.
Both application containers and MySQL are healthy. Frontend/session HTTP reads
succeeded; guest employee administration returned 401. S04 capability catalog
is present. Users, roles, role_permissions, orders, bills, payments and payrolls
counts/checksums match the predeployment snapshot, as do exact role assignments
and pending-account IDs. No mutation acceptance tests ran on the working DB.
Initial counts: 27 users, 7 roles, 118 grants, 32749 orders, 10053 bills,
3618 payments, 526 payrolls. New permissions were not assigned automatically.

S04 is FIXED for Phase 1; deferred Phase 2 prevents a fully verified migration
claim. Explicit operator grant decisions remain necessary for staff delegation.
Git commit/push and exact VM checkout reconciliation follow the successful
deployment; their results must be recorded separately. S05 is next.

S04 Git publication completed after successful deployment: backend 1134fc5 on
origin/fix/mysql-runtime; frontend ca82138 on origin/main. Both VM repositories
fast-forwarded cleanly to those exact revisions. Compared deployed candidate
employee API/UI source against checkout source successfully. Final frontend,
backend and MySQL health checks passed; HTTP session read succeeded. Running
application images remain the explicit candidates via the preserved override;
future Compose operations must include that override or deliberately rebuild
the synced checkouts. Backup and previous image tags remain available.

## S05 parent-document authorization — 2026-11-26

Inspected archived report controller, report models/contracts, current bill/order
detail, all report discovery/form/generation handlers and frontend callers.
Confirmed report handlers had authentication-only access independently of domain
read checks. Added shared bill/order read helpers and used them for detail and
report consumers. Bill documents require view_accounting_bills; Orders documents
(including raw calculation transcripts) require view_menu_orders. The bill-linked
order-document collection requires both. Existing bill-document linked order
summaries remain bill-scoped as in bill detail; raw order reports do not inherit
bill-read authority. Shared-team visibility is retained; no owner-only rule or
new export grant was invented. Settings authority does not imply document access.

Discovery, form metadata and GET/POST generation reject deleted parents even
with view_trashed; missing/unknown/deleted report and parent IDs are independent.
Authorization precedes rendering. Updated permission manifest; payroll remains
under its existing separate policy. No role grants or financial formulas changed.

First real-session run failed fixture setup (missing order status); corrected
fixture and reused session helpers without inheriting unrelated employee tests.
Six focused SQLite cases then passed; existing 15 report tests passed. Expanded
matrix covers all eight supported report types, both generation methods, repeated
denials/all-table snapshots, guests, pending/unrelated staff, domain readers,
deleted/missing parents, unknown models and revocation. Six cases passed on each
guarded disposable MySQL InnoDB/MyISAM schema, no skips. Local backend image built.
Full backend run completed: 589 tests OK, including 200 opt-in skips. Full
isolated browser run completed: 22 workflows and 19 frontend helper tests passed.
Final review corrected a manifest-only description accidentally placed under
pricing; pricing policy is unchanged. No scenarios.md edits. Backup, deployment
and push have not started for S05: SSH key authentication was denied and no
S04_SSH_PASSWORD is available in the resumed process environment. Existing live
deployment is unchanged; do not mark S05 deployed until verified backup, rollout,
health/data checks and publication complete.

### S05 deployment attempt — 2026-11-26

SSH access restored using process-only credentials. Verified clean VM checkouts
(backend 1134fc5, frontend ca82138), healthy S04 images and actual MySQL volume
rework_mysql_data. Fresh locked dump, checkout/config and data archives verified
with gzip/tar and SHA-256 at /root/backups/s05-20261126T095151Z; rollback image
tags retained. No restore rehearsal. Uploaded source archive SHA-256
6e2f2afb69540fe8351a126932ed23bea1bf64d21c6abda3cf4cff2c3df065a8;
both VM S05 candidate images built.

First attempt reached healthy candidate containers but an operational checker
indentation error triggered automatic application rollback; corrected checker.
Second attempt reached healthy candidates but integrity comparison detected bills
count 10057 -> 10058 and checksum 2954883252 -> 3442940039. Other compared
business tables, role grants and pending accounts were unchanged. Automatic
application rollback completed; frontend/backend/MySQL healthy and session health
endpoint passed. Do not assume concurrent activity explains the added bill.
Paused pending investigation/operator confirmation; no database restore, deletion,
grant broadening, Git commit/push or VM checkout synchronization performed.

### S05 successful rollout — 2026-11-26

Operator confirmed the extra bill was created by another developer and authorized
continuation. Preserved that data; took a new locked backup at
/root/backups/s05-20261126T101416Z, verified gzip/tar and SHA-256, and retained
rollback images. No restore rehearsal. Fresh baseline includes 10058 bills.
Application-only rollout succeeded with s05-candidate-backend and
s05-candidate-frontend; both healthy, MySQL unchanged and healthy. Compared
users/roles/role_permissions/orders/bills/payments/payrolls counts/checksums,
exact role grants and pending accounts: unchanged. Existing S04 permission catalog
preserved. Session/home health checks passed. Active deployment uses existing
Compose files with --profile mysql and /root/backups/s05-candidate-images.yaml.
Actual database volume remains rework_mysql_data. No working-database mutation
QA or automatic grant changes performed. Git publication/synchronization follows.

Publication completed: backend implementation a0fae30 on fix/mysql-runtime and
frontend e76d75c on main pushed successfully. Both VM checkouts fast-forwarded
to those revisions with clean working trees; deployed application sources match
the staged candidate. Independent verification passed: all three service health
states healthy, report discovery/form/generation guest denials 401, deployed
report/resource-read hashes match candidate, actual MySQL volume and rollback
images retained. Session health passed after checkout synchronization. S05 Phase 1
is complete; Phase 2 remains deferred. Next finding is S06.

## S06 bill/payment deletion authorization — 2026-11-26

Confirmed bills and bill-owned payments used edit authority for DELETE/restore.
Implemented shared lifecycle policy: view_accounting_bills AND existing
delete_accounting_bills; restore additionally requires restore_trashed and
permanent deletion additionally requires delete_trashed. Payments deliberately
share bill-delete authority rather than introducing/auto-granting a new permission.
Payment lifecycle requires an active matching bill; restore the parent first.
Delete does not require edit; editors without delete can still save.
API capability flags and bill/payment controls now distinguish edit from delete.
No grant/bootstrap changes, working-database mutation QA or scenarios.md edits.

Four real-session regressions cover repeated denied requests with all-table
snapshots, editor saves, trash-only/delete-without-read denial, domain+lifecycle
success without edit, parent mismatch/deleted parent, and grant revocation.
Focused run: 13 tests passed. Isolated MySQL: four passed on InnoDB and four
on MyISAM. Backend Docker image built. Local frontend build could not start
because local Vite dependencies are absent; existing disposable browser harness
installs lockfile dependencies. Full backend and browser validations started;
S06 backup/deployment/commit/push not started.

Full first run: 597 tests, one failure (old session test expected edit-only
payment deletion). Updated test to assert edit-only denial then explicitly grant
delete before ownership/lifecycle assertions; full rerun started. Existing 22
browser workflows passed. Added synthetic bill-editor fixture and dedicated S06
browser case; first run served stale prebuilt frontend and found the legacy delete
link, so current frontend image rebuild and browser rerun are required before
acceptance. Do not interpret the stale-image run as validating the changed UI.

Validation completed after rebuilding the frontend image: full backend 597 tests
OK (204 opt-in skips); 23 browser workflows including S06 and 19 frontend helper
tests passed. Both application images built locally and on VM. New locked backup
verified at /root/backups/s06-20261126T103926Z (gzip/tar and SHA-256; rollback
images retained, no restore rehearsal). Candidate archive SHA-256
1b746e6a1373ba2826032207b9607b71b5df072b90fe4538e2e4ffaf3d4a70d8.
Fresh baseline: 10058 bills; other business counts and pending account [28]
recorded. Application-only deployment started; integrity/health verification and
Git publication remain required before marking complete.

S06 rollout succeeded: s06-candidate-backend/frontend healthy, MySQL unchanged
and healthy. All compared business counts/checksums, exact role grants and pending
accounts unchanged, including 10058 bills. S04 permission catalog preserved.
Existing Compose files plus --profile mysql and
/root/backups/s06-candidate-images.yaml select deployed images. Actual MySQL
volume rework_mysql_data preserved. Session/home health passed. No working DB
mutation QA, grants broadened, or scenarios.md changes. Publication follows.

Publication complete: backend ad2ef07 (fix/mysql-runtime) and frontend 68a951c
(main) pushed and VM checkouts fast-forwarded cleanly. Deployed accounting helper,
bill and payment source hashes match candidate; independent service/volume/
rollback-image/session checks passed. Checkout source comparisons passed and
session health remained good after synchronization. S06 Phase 1 complete; next
finding S07. Phase 2 stays deferred.

## Approved accountant payer-edit grant — 2026-11-26

Operator explicitly approved payer creation/editing for existing accountants.
Resolved unique live role Бухгалтерия (id 7), required existing payer-read grant,
snapshotted roles/exact role_permissions under /root/backups/accountant-payer-grant-*
and serialized update through security_writer. Added only edit_accounting_payers;
verified no removals or unrelated additions before commit. First result reporting
failed JSON serialization after successful commit; idempotent retry confirmed
effective grant true with zero further additions/removals. Retry snapshot at
/root/backups/accountant-payer-grant-20261126T110203Z. No payer/business data was
created or changed; no delete/admin grants added. This is an approved operational
grant, not an automatic bootstrap policy change.

## S07 initial credential-reset increment — 2026-11-26

Inspected finding, employee reset/update, session password fingerprints, persistent
remember authentication, public password reset and existing real-session tests.
Confirmed employee password reset left remember_token intact. Shared
credentials.replace_password now sets password hash and clears remember digest;
employee and public reset use it in their existing commit. Added real cookie
regression: old password/session/remember rejected, new password accepted, unrelated
actor session retained. Focused run: five tests passed (new case plus existing
SQLite session suite). No S07 deployment/commit/push yet. Still required: policy
and coverage for firing/deletion/restoration/email/role changes, missing-fingerprint
compatibility, remember use/rotation decision and historical MySQL atomicity;
full regression/MySQL/browser validation and normal backup/rollout sequence.

### S07 security-stamp increment

Added nullable per-user security_stamp and additive migration 2026-11-26-01.
Password replacement rotates stamp and clears remember digest together on the user
row. Employee email/role/fired transitions and soft-delete/restore do likewise;
ordinary profile edits do not. Session validation requires password fingerprint
and matching stamp; missing-password-version compatibility bypass removed.
Login/registration/remember authentication record the current stamp. Existing
unstamped sessions with a valid password fingerprint remain compatible until a
revoking event. No automatic role grant or credential-data rewrite in migration.

Real-cookie lifecycle regression covers email/role changes, firing then unfiring,
delete then restore, ordinary profile edit continuity and unrelated actor session.
Focused session/employee run: 30 tests OK, 12 opt-in skips. Two S07 cases passed
on each isolated MySQL InnoDB/MyISAM engine. Added repeatable migration-preservation
test afterward; validation pending. Full backend run started. Still open: complete
suite/schema compatibility feedback, remember rotation decision, concurrency/reset
atomicity review, browser/build and backup/schema rollout planning. Not deployed.

### S07 serialized writers and recovery consumption

Initial full suite: 601 tests OK, 206 opt-in skips. Added security_writer to
login, password-email and public-reset aliases to serialize against employee
credential changes. Recovery material is consumed before credential updates;
MyISAM can lose a recovery token on failure but cannot claim transactional
rollback across tables. Password/stamp/remember update stays on one user row.
Employee security events discard prior recovery tokens. Remember tokens replace
on remembered login and revoke on security changes, not on every parallel request.
Policy/rollout constraints documented in docs/s07-credentials.md; S08 remains
separate. Nine focused tests passed; backend image rebuilt. Five S07 cases passed
on each disposable MySQL engine; existing 23 browser workflows and 19 helpers
passed. Added old-column migration preservation and real browser-cookie reset
cases afterward; their MySQL/browser reruns are in progress. No S07 server schema
change, deployment, commit or push yet. Approved accountant grant stays intact.

Latest full validation: 607 backend tests OK, 209 opt-in skips. Six S07 tests
passed on each disposable MySQL engine, including actual old-column preservation
across repeated upgrade. All 24 browser workflows (including saved session and
remember-cookie rejection after employee reset) and 19 frontend helpers passed.
Fresh locked backup /root/backups/s07-20261126T131043Z passed archive/SHA-256
verification; rollback images retained, no restore rehearsal. Uploaded archive
SHA-256 3940fb660f7711b39869c316df6ad8b4e9621fda6146e604bbbef3b3c46a3d08;
both candidate images built on VM. Schema-aware rollout started; additive column
is retained on image rollback. Existing user values compared via logical digest
excluding new column, other business tables via counts/CHECKSUM, exact grants
including approved accountant payer-edit assignment preserved by assertion.
Rollout verification and publication pending.

First schema rollout stopped on MySQL 1067 invalid created_at default (historical
zero-date users column). Automatic rollback restored healthy S06 images. Updated
additive migration to temporarily use session-local NO_AUTO_VALUE_ON_ZERO and
restore the original SQL mode in finally, matching existing compatibility pattern.
Extended disposable MySQL migration test with zero-date created_at default and
SQL-mode restoration assertion; reruns pending. Do not mark S07 deployed.

Zero-date test initially failed in test fixture DROP COLUMN preparation, not the
updated migration; corrected preparation SQL mode. Six S07 tests then passed on
each MySQL engine (including old-column preservation and original mode restored).
Six focused SQLite tests passed. Repackaged candidate SHA-256
365c6ae38c744faf7ea6195516ea19f685b2f73e60665d943eeb73615f808508,
VM candidate-v2 images built; second schema-aware deployment started.

S07 deployment completed. Migration command consumed remaining streamed shell
stdin after successful DDL; corrected with /dev/null and resumed application-start
and invariant checks in a separate script. All services healthy. Existing user
column digest, business table counts/checksums and exact grants matched baseline;
new stamps all null as intended, accountant payer-edit grant preserved. No business
mutation QA or automatic credential rewrite. Active Compose override:
/root/backups/s07-candidate-images.yaml with --profile mysql; rework_mysql_data
preserved. Backup /root/backups/s07-20261126T131043Z and rollback tags retained.
No restore rehearsal. Publication and independent verification follow.
