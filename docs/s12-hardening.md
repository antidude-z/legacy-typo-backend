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