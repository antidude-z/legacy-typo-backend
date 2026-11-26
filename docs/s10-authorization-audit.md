# S10 — route authorization inventory and enforcement evidence

## Scope and invariant

Every business APIRoute method/path/module entry must exist in the checked-in
`app/reviewed_routes.json`, select valid contracts from `app/route_policies.py`,
and retain the shared staff-admission dependency. A new route must not become
approved merely by matching a family wildcard, an auth prefix, or the presence
of permission IDs in the database.

The baseline is deliberately not regenerated during tests. When a route changes,
review its handler, aliases, resource scope, payloads, grant conjunctions and
real-session regressions before updating the baseline. Dynamic dictionary/work/
inventory routes name all applicable domain contracts; conditions explain the
selector, lifecycle, parent and target rules.

`route_coverage.complete` means inventory/policy-reference/admission coverage,
not executable certification of every handler. The endpoint retains
`enforcement_verified: false`. Catalog completeness, declared contracts, runtime
inventory and recorded test evidence remain separate. No grant is added by this
audit, and no security decision is based on role titles.

## Changes

- Inventory comes from `app.routes`, including all methods, nested paths,
  collection routes, reports/exports and compatibility aliases. Added/changed,
  missing, unclassified, invalid-policy and missing-admission cases are reported.
- Public health/root/session/CSRF and authentication/reset workflow exclusions
  are exact method/path pairs. A newly added route under `/api/auth/` is not
  silently excluded. Framework OpenAPI/documentation routes are not APIRoutes
  and are outside business-policy coverage; deployment/discovery are S11/S12.
- Permanent regressions inject new methods/routes, remove a reviewed route and
  remove its admission dependency using separate test applications. Normal
  unittest discovery fails on unreviewed route additions.
- Fixed catalog omissions (`delete_accounting_bills`, role-assignment and
  credential-reset authority), included employee DELETE and corrected stale
  report/main-options policy descriptions.
- Existing S01/S03/S04/S05/S06 real-session suites cover domain actions, lifecycle
  conjunctions, privileged targets, grant revocation, ownership/trash and
  unchanged-state denials. Policy entries link those suites explicitly.
- Added real-session residual coverage for pricing, report settings, payroll,
  main options, production diagnostic denial, permission administration and first
  employee deletion/revocation. Requests use valid payloads and CSRF with actual
  cookies/grants, not a universal permission mock. Full table snapshots assert
  unchanged state on denied requests.

## Confirmed additional gap: payroll reader GET writes

Payroll draft detail/export GET previously refreshed and committed statement
rows with only `view_menu_reports_payrolls`. Readers now receive stored data
without refresh writes. An editor with both read and edit grants retains the
existing draft refresh behavior; POST/PATCH remain edit-authorized. Tests include
an eligible order, proving the unchanged reader snapshot is not a vacuous
empty-fixture assertion, then prove an editor can refresh it.

The API returns `can_edit`; payroll controls and submit handlers fail closed on
that capability and the existing paid-state UI rule. A browser reader test checks
disabled salary/status/save/create controls, a direct PATCH denial and preserved
salary. Existing privileged-target/employee capability and bill lifecycle browser
checks remain in the acceptance suite.

This is authorization containment, not a repair of F09/F10 payroll formulas,
duplicate eligibility or paid-statement reopening semantics. Editors can still
trigger draft refresh through GET, an explicitly documented compatibility rule.

## Local Phase 1 validation — 2026-11-27

All mutation tests used in-memory SQLite, owned Docker tmpfs fixtures or guarded
separately named disposable MySQL. No working/live database was mutated.

- Final backend: `python -W error -m unittest discover -s tests -q`:
  **634 tests, OK, 218 opt-in skips**.
- Final focused audit/permissions/residual grants: **21 tests OK**. The earlier
  focused run including payroll compatibility tests passed **25 tests**.
- `python -m scripts.s04_mysql_qa --finding S10`: **6 tests InnoDB and 6 tests
  MyISAM, all OK**, with isolated guarded databases and cleanup.
- Frontend `npm.cmd test`: **21 helpers passed**.
- Backend/frontend Docker builds succeeded; frontend production Vite build
  succeeded in the locked-dependency Docker environment. The initial host build
  could not start because local Vite dependencies were absent; it is not counted
  as a successful build.
- `python -m scripts.s04_browser_qa`: **25 browser workflows passed**, including
  the new payroll-reader check. Owned containers use synthetic data, not live
  service endpoints.
- Both repository diffs passed whitespace checking.

Saved local evidence is under the workspace root: `s10-acceptance-full-err.txt`,
`s10-acceptance-mysql-{out,err}.txt`, `s10-final2-err.txt`,
`s10-final2-ui.txt`, `s10-browser-{out,err}.txt`, and
`s10-{backend,ui}-image-err.txt`.

## First rollout attempt and rate-seed blocker

The S10 source commits were published and a verified live backup was captured at
`/root/backups/s10-20261126T200725Z`. All-table invariants detected seven new
`rates` rows on candidate startup. Automatic application-image rollback restored
healthy S09 services; restarting S09 added another seven rows. No live rows were
deleted and no database backup was restored to conceal these differences.

Read-only investigation confirmed historical `rates.usd/eur` are DECIMAL(10,2),
while bootstrap looked for unrounded four-decimal constants. This pre-existing
startup bug duplicated seven seed rates on every restart. The follow-up uses
reflected column scale and Decimal ROUND_HALF_UP for both lookup and insertion;
it does not rewrite existing rates or modify schema. A disposable MySQL
regression uses the exact historical two-decimal columns and verifies repeated
initialization preserves every rate row on both storage engines.

A fresh backup and baseline are required before retry. Phase 2 remains deferred;
the scenario specification was not read or executed.