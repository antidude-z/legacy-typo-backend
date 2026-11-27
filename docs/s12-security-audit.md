# S12 security event contract and operator runbook

## Private storage and coverage

`/app/data/security-audit.db` is a SQLite audit journal on persistent backend data,
mode 0600, synchronous FULL, separate from business tables and MyISAM. Optional
SECURITY_AUDIT_DB must point to protected persistent storage. No HTTP viewer or
new role grant exists: review is limited to host/container operators. Existing
security-administration authorization remains unchanged.

The serialized security writer journals employee create/update/delete/restore,
permission-matrix writes and applied operator role assignments. Staff-admission
denials on employee/matrix mutations are also recorded. Events contain random ID,
UTC epoch timestamps, authenticated actor ID (null for guests/operator CLI),
target ID, action, outcome and allowlisted before/after state: role ID, fired and
deleted flags, existence, permission-grant IDs, credential-reset-requested and
email-field-supplied booleans. CLI includes host operator UID where available.
No submitted name/email, password/hash, reset token/link, cookie, request body,
exception text or arbitrary URL is recorded. Application-owned paths and numeric
target IDs only; CLI email selectors resolve to IDs without logging the selector.

Validation/CSRF/routing failures before a security handler are not all audit
events; this is administrative auditing, not a general request/access log.
Direct DBA SQL and other noncooperating writers are outside application coverage.
All database maintenance must stop application writers and retain separate DBA logs.

## Failure and reconciliation policy

1. Persist an intent before executing the administrative handler. If the audit
   store is unavailable, return 503 before mutation.
2. Existing business transactions and last-admin locks remain authoritative.
3. Record success, denial or error afterward. A crash leaves a durable intent.
4. MyISAM commits and the independent journal cannot be atomic. Outcome-write
   failure after business commit returns 503 requiring operator reconciliation;
   it never claims rollback. Structured logs carry only the event ID.
5. Do not blindly retry an ambiguous mutation. Inspect the event, compare current
   target/grant state and the protected backup, then resolve operationally. Keep
   the original event unchanged; preserve reconciliation evidence in the incident
   record. This is crash-durable journaling, not cryptographic tamper protection
   against a root/DBA adversary.

## Retention, review and alerts

Initial retention policy: **retain indefinitely; no automatic pruning**. Include
the journal in protected backend-data backups, restrict backup access and monitor
disk space. Full disk fails privileged writes closed. Any later retention change
requires a reviewed, backed-up operator change; never silently truncate the file.

Host operator commands (read-only, bounded output):

```sh
docker exec rework-backend-1 .venv/bin/python -m app.security_audit --limit 100
docker exec rework-backend-1 .venv/bin/python -m app.security_audit --alerts --limit 10000
```

Run alerts at each administrative maintenance window and review structured service
logs. Denied/error outcomes emit event-ID-only warning records. Five employee
delete attempts within 300 seconds emit a bulk-delete warning. The restricted
viewer reports unresolved intents, denied/error records and bulk-delete patterns;
its output explicitly states its latest-N bound. Integrate these structured log
records with the site's existing monitoring when available; no external alert
destination or notification delivery is assumed or silently configured.

## Generic public responses

Opt-in registration validates input without an existence-specific error, hashes
valid submissions on either branch, and returns the same no-store HTTP 200 message
for new/existing email. New accounts remain roleless pending approval; registration
does not authenticate them. Disabled registration still returns 403 for everyone.
The SPA shows the generic result, clears password fields and does not redirect
into an authenticated workflow. Login remains explicit.

Reset initiation returns the same no-store HTTP 200 response for unknown accounts,
successful delivery and delivery failure. A failed send emits only a fixed
operator diagnostic and does not replace a prior token. Delivery precedes token
persistence; storage failure after successful SMTP delivery remains an operational
error, not a claim of guaranteed delivery. Disabled mail gives a configuration-
wide 503. Existing token validation, expiry, revocation, CSRF and abuse limits
remain active. No claim of constant-time SMTP/network behavior is made.