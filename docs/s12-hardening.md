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

## Discovery rollout evidence

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

## Abuse-control implementation increment (not deployed)

`app/auth_abuse.py` adds atomic SQLite account/IP/global budgets, shared across
both aliases and workers using LOGIN_LIMIT_DB. Every accepted attempt consumes
all three budgets in one BEGIN IMMEDIATE transaction; rejected attempts consume
none. Expired rows are removed. Successful login does not reset these independent
spray budgets; the older failure limiter remains in place. Account keys are
case-folded and only SHA-256 identifiers are stored (not encryption/anonymity
against offline guessing by a privileged file reader). Storage failure returns
generic 503 before business/auth side effects.

Fixed 15-minute budgets (account/IP/global): login 20/100/1000; registration
3/10/100; reset initiation 3/10/100; reset consumption 10/50/500. Returns 429 with
Retry-After 900. Production always enables this control. HTTP validation requires
explicit AUTH_ABUSE_ENABLED=true; isolated endpoint tests patch only enablement
and point the store at a TemporaryDirectory. This is a single-host persistent
volume solution, not a distributed/multi-host limiter. Forwarded identity is not
trusted: proxy users may share an IP budget. Threshold tuning requires review.

Exact authentication POST aliases (including slash-normalized paths) have a
16 KiB actual-byte cap before form parsing; streamed/chunked bodies are counted,
not trusted based on Content-Length. Form fields cap email/name at 255, password
and confirmation at 72 characters (existing bcrypt byte checks still apply), and
reset token at 256. Field validation precedes hashing, mail and account lookup;
body limiting does not implement connection timeouts or replace proxy DoS controls.

Final expanded focused run: **21 tests OK**, including real endpoint CSRF,
alias sharing, no token replacement/mail after denial, storage failure, atomic
concurrency, expiry, IP/global ceilings, field/body bounds and enabled-registration
denial without hashing or account creation. Full run started before the final
added regression/body-cap refinement: **656 tests OK, 221 skips**, exit 0,
188.385s (`s12-abuse-full-result.txt`). It is not an exact-final-tree full pass.
Fresh backend/frontend builds, frontend production build, **21 helpers** and
**26 browser workflows** passed (`s12-abuse-browser-result.txt`, 42.6s). The
browser fixture does not enable the new budgets, so this proves compatibility,
not enabled-budget browser acceptance. Final focused result:
`s12-abuse-final-err.txt` (21 tests OK, 7.955s).
No deployment, live limiter probes or working-data mutations occurred in this
increment. Before rollout, enable the HTTP VM via a persistent Compose overlay,
verify owned-store persistence, back up, deploy and compare business invariants.

## Remaining S12 work

Final acceptance increment: **665 backend tests OK, 229 opt-in skips**, exit 0,
193.564s. **8 auth-side-effect tests per InnoDB/MyISAM engine passed** against
owned guarded historical FK-free schemas. Limiter files remained test-owned.
The first enabled browser run hit its account budget after repeated synthetic
logins (24 workflows passed, 2 setup logins denied). Thresholds were not weakened:
browser acceptance now uses two fresh owned stacks (3 accessibility workflows,
23 business workflows), with enforcement enabled and the same default budgets.
Enabled browser and cross-container persistence completion remain pending.
Superseded by completed acceptance: **3 accessibility + 23 business workflows
passed**, enforcement enabled with unchanged default thresholds on separate owned
stacks. Owned limiter volume survived container recreation and rejected the
fourth registration reservation. No working limiter file was used for those tests.

## Abuse-control rollout — 2026-11-26 UTC

Implementation `21350682417d68b2ff165df2f522defcd9d1a581`, frontend unchanged
`5f1d4a58edf66ae1fbd3fcddc484e8da1060cb9d`. Verified source SHA-256:
`a780f808004a4199f601cade967b30224b8bc0adddb0649a579c6297a9a8e97f`.
Fresh verified backup `/root/backups/s12a-20261126T214555Z`; archives and checksums
passed, including independent verification after restart.

Persistent HTTP enforcement is enabled in the existing `compose.mysql.yaml`
backend environment; tracked `compose.auth-abuse.yaml` was also installed.
The original launch overlay is retained in the backup for image/config rollback.
LOGIN_LIMIT_DB remains `/app/data/login-limits.db` on the persistent volume.
HTTP/cookie/TLS settings and MySQL volume `rework_mysql_data` were retained.

Deployment, independent verification and synchronization returned
`S12A_DEPLOYMENT_OK`, `S12A_VERIFY_OK`, `S12A_SYNC_OK`, SSH exit 0. Services
healthy; all-table count/checksum, exact user and grant invariants unchanged,
including accountant payer-edit authority. Source hashes, 179 reviewed routes,
CSRF and empty-roster probes passed. Both resolved launch configuration and live
environment confirm AUTH_ABUSE_ENABLED=true. Oversized auth POST returned 413
without consuming real account budgets; invariants compared again afterward.
Live throttling was not exercised against staff accounts. Evidence:
`s12a-{backup,backup-check,stage,deploy,verify,sync}-result.txt`,
`s12a-persistence-result.txt`, `s12a-browser-result.txt`.

## Still open
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