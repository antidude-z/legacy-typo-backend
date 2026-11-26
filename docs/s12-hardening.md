# S12 — discovery, abuse controls and security auditing

Status: **in progress**. No Phase 2 scenario execution is claimed.

## Discovery increment

Invariant: neither public login-roster alias may disclose staff identities.
`GET /auth/users` and `/api/auth/users` retain their compatibility URLs and return
an empty object with Cache-Control: no-store. The handler no longer queries users.
The SPA no longer fetches the roster; login requires a typed email address with
browser username autocomplete instead of selecting an advertised employee.
This does not change password verification, staff admission or permission policy.

Inspected legacy AuthController/PasswordController, active auth/session handlers,
employee and matrix writers, models used by their callers and existing real-session
tests. The public roster was source-confirmed; removal deliberately improves on
inherited behavior rather than copying a discovery weakness for parity.

Permanent backend tests cover both public aliases, no-store, no name/email in
responses and successful typed-email login. Browser workflows now fill the email
input; an additional workflow checks no roster fetch, empty initial value and
successful login without directory lookup. Non-login dropdowns are unchanged.
Initial focused authentication/discovery/route-inventory run: **16 tests OK**.
Full backend suite: **648 tests OK, 221 opt-in skips**, exit 0 in 183.572s
(`s12-full-result.txt`). Fresh image builds and frontend production build passed.
The first browser run exposed a stale setup assertion waiting for a removed email
dropdown option; the new discovery workflow itself passed. The assertion now
waits for the typed-email input; clean full browser rerun is required before release.
No migration, grant change or historical account repair is required.

## Remaining S12 work (not claimed implemented)

Discovery rollout completed 2026-11-26 UTC. Backend implementation:
`a3e1d4b5e10c9dfa3cbf2f12b8cc709a5fa5f5a8`; frontend:
`5f1d4a58edf66ae1fbd3fcddc484e8da1060cb9d`. Clean browser rerun:
**26 passed**, 40.7s, including the new discovery workflow; **21 frontend helpers**
passed. Both application images and production frontend build passed.

Fresh verified backup: `/root/backups/s12-20261126T212401Z`. Source SHA-256:
`4de8d50501ccd7f27dbaab87ef3ab4e03e6b26fd311f6959db9488afd2e0c450`.
Database, checkouts/config and backend-data archives passed integrity/checksums.
Deployment, independent verification and synchronization returned
`S12_DEPLOYMENT_OK`, `S12_VERIFY_OK`, `S12_SYNC_OK`, each SSH exit 0. Services
healthy; all-table counts/checksums, exact users and role grants unchanged,
including accountant payer-edit authority. MySQL volume `rework_mysql_data`
retained; no schema or account repair. Source hashes and 179 business-route
inventory entries verified; prior CSRF probes passed. Both roster aliases were
verified empty/no-store directly on the backend, and the SPA proxy response was
also empty. VM checkouts clean at released implementation revisions. Evidence:
workspace `s12-{backup,backup-check,stage,deploy,verify,sync}-result.txt`.

- Account/IP/global limits for login, registration, reset initiation and reset
  consumption; aliases must share budgets. Bound request and field sizes before
  expensive password hashing/mail/database processing. Shared durable state must
  fail closed and use test-owned paths in regressions, not working data files.
- Generic registration/reset responses, including mail delivery failure behavior,
  must avoid revealing whether an account exists while preserving operator diagnostics.
- Dedicated durable security events for employee lifecycle, role/credential changes,
  permission matrix and operator role CLI, including denial/error outcomes.
  Record actor/target/action and allowlisted safe before/after metadata; never
  passwords, hashes, email addresses, reset links or tokens.
- Explicit write-ahead/outcome/failure policy for MyISAM: business commits and an
  independent audit store cannot be represented as one atomic transaction.
  Test fail-closed intent persistence and reconciliation of ambiguous outcomes.
- Decide retention/rotation and restricted operator viewer, plus denied-action and
  bulk-destructive alerting policy. Existing order Action records are not a
  substitute for a durable administrative security audit.

S11 production TLS activation is still a separate blocker. Do not equate roster
removal or valid CSRF with complete S12/production readiness. Back up and verify
business/user/grant invariants before deploying each completed slice.