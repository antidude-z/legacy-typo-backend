# S11 — production launch and cookie-authenticated CSRF

## Invariant

Every unsafe request carrying a session, remember-me or CSRF cookie requires a
cookie/header token matching the signed session token, regardless of APP_ENV.
Deleting or emptying the CSRF cookie cannot opt a browser out. Production also
requires the token for anonymous login/register/reset requests. There is no
stateless API credential implementation; the cookie-free development compatibility
exception is not production API authentication. Permission checks remain separate.

The legacy VerifyCsrfToken middleware delegated to Laravel's verifier. The
rework's old development exception only examined the CSRF cookie, allowing
session/remember cookies to remain while skipping verification. New regressions
cover that omission, empty cookies, forged double-submit pairs, signed-session
binding, all unsafe methods and registered aliases. Real-session tests use an
isolated SQLite fixture, actual bcrypt login and all-table denial snapshots.

## Launch contract

Base Compose remains explicitly local/validation. Production adds
`deploy/compose.production.yaml`: enforced production mode, secure cookies,
required HTTPS origin/signing secret, loopback-only publication via `!override`
(Compose 2.24.4+), and `--no-proxy-headers`. Startup rejects unknown APP_ENV values
and unsafe production configuration. APP_URL must be an origin, not a path,
credential-bearing URL, query or fragment. No database/schema change is needed.

No forwarded identity is trusted in this conservative topology. Existing durable
single-host login limits remain enabled in production and may group clients
behind the proxy. SMTP policy and S12 abuse/auditing are unchanged.

## Acceptance and rollout limits

Initial focused run: 19 tests OK, 4 opt-in MySQL skips. Expanded focused run:
13 tests OK, including every registered unsafe route/alias. Resolved production
Compose was checked against hostile development/nonsecure/LAN environment inputs:
production and secure cookies stayed forced, frontend published only on loopback,
backend/MySQL had no published ports, and proxy header trust was disabled.

Fresh backend/frontend image builds and frontend production build passed;
**25 isolated Chromium workflows** passed, with the existing **21 frontend helper
tests** run by the same harness. Final focused security/deployment checks:
**18 tests OK**. Including corrected bill/material filter fixtures:
**28 targeted tests OK**. S11 real-session MySQL regressions: **2 tests InnoDB
and 2 tests MyISAM, all OK**, using the guarded disposable tmpfs harness.

The first full backend run reported 643 tests, 219 skips and three failures:
older bill/material filter fixtures established a session then mutated it without
CSRF. Those fixtures now obtain a real token and send it, without bypassing
middleware. A full rerun was started; no successful completion is yet recorded.
Evidence: workspace `s11-{full,full2,final-targeted,mysql}-err.txt`,
`s11-browser-result.txt` and `s11-compose-result.txt`.

No live VM configuration was inspected or changed in this increment.
TLS certificate/origin, external HTTPS reachability and local proxy setup must be
verified before enabling secure cookies on the VM; otherwise HTTP users would be
locked out. Do not apply the older validation-volume overlay without confirming
the actual live volume mapping. Back up and retain rollback images before rollout.

Final fresh verbose full suite: **646 tests OK, 221 opt-in skips**, exit 0,
177.174 seconds (`s11-full3-result.txt`). The earlier quiet rerun stalled and
was stopped; it is not counted as successful. Read-only VM preflight confirmed
healthy S10 services, clean checkouts, 64-character signing secret, development
mode, nonsecure cookies, HTTP APP_URL and only LAN port 8080 (no 80/443 listener).
The containment rollout preserves those validation settings; production overlay
activation remains blocked on provisioned, externally verified TLS.

S11 remains in progress pending backed-up rollout and production TLS acceptance. Phase 2
is deferred; no scenario specification was opened or executed.