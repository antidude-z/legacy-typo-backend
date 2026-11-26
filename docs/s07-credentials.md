# S07 credential revocation policy

Password reset (employee administration or either public reset alias) replaces
the password, clears the remember digest and rotates a per-user security stamp.
Employee email/role/fired transitions and soft-delete/restoration also rotate
the stamp and clear the remember digest. Ordinary profile changes do neither.
Other users' sessions are unaffected. Existing role permissions are read on every
request; permission-matrix edits do not rotate all members' sessions.

Signed sessions require the current password fingerprint and matching stamp.
Missing password fingerprints are rejected. Existing fingerprinted sessions on
accounts with a null stamp remain compatible until a revoking event occurs.
The stamp is never returned by employee APIs or written to change-history text.

Remember tokens are random, stored only as digests, signed and time-limited.
Each remembered login replaces the previous persistent token for that account;
existing ordinary sessions remain valid. Remember authentication does not rotate
on every request: parallel-tab requests and the single-digest storage contract
would otherwise invalidate each other. Security events revoke it independently
of the browser accepting a replacement cookie.

Login, recovery-token issuance, public reset and employee security writers share
the cross-process security lock. Recovery tokens are consumed before credential
updates. Password/stamp/remember changes are a single users-row update. MyISAM
cannot roll back multiple tables: a failure may consume recovery material without
changing credentials, requiring a fresh recovery request, but must not leave a
consumed token reusable after a successful password change. No full transaction
atomicity is claimed for MyISAM. Logout session revocation is separately S08.

## Rollout

Migration 2026-11-26-01 adds nullable users.security_stamp; it does not rewrite
historical credentials, grant roles or initialize stamps for all users. Stop
application writers, take/verify a locked backup, apply only the reviewed additive
migration, compare old-column logical user digest and business/grant invariants,
then start the candidate. A physical users CHECKSUM may change due to the new
column, so compare existing user column values separately. Retain rollback images
and the additive column on application rollback; do not drop it or restore data
automatically. Maintenance excludes simultaneous operator SQL writes.