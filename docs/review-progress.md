# Phase 1 review remediation

Phase 2 has not started. Focused Phase 1 tests are not scenario executions.
Scenario report pairs will be initialized at Phase 2 entry as required by scenarios.md.

## Finding register

| Finding | Status | Evidence / next step |
|---|---|---|
| S01 | in progress | Employee read/delete/restore gates and UI capabilities implemented; real-session SQLite regressions added. Self-disable, privileged-target, last-admin and concurrency protection remain release blockers. |
| S02 | unstarted | Public registration / pending-account containment. |
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