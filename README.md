# Typography backend

FastAPI compatibility backend for the legacy typography application.

## Local database initialization

The default local database is SQLite at `data/typography.db`.  Initialize it
explicitly with:

```text
uv run python -m app.bootstrap
```

Application startup runs the same additive initializer automatically.  The
project-owned migration runner in `app/schema.py` creates the empty model
baseline, applies tracked migrations in order, and records them in
`schema_migrations`.  The initializer then records the application catalog
version in `schema_versions` and idempotently adds only legacy-confirmed catalog data:
roles, permissions, role-permission assignments, order statuses, report
definitions, and report parameters.  Existing business rows and assignments
are preserved; the legacy SQL dump is not imported.

To use another database, set `DATABASE_URL` before running the command.  A
MySQL URL is supported through the same SQLAlchemy configuration used by the
application.

To inspect/apply tracked schema migrations directly:

```text
uv run python -m app.migrate status
uv run python -m app.migrate upgrade
```

This establishes the rework migration history; it does not import the legacy
MySQL dump.  Dump conversion and live MySQL verification remain separate tasks.

To regenerate the dump/model schema-name comparison without importing data:

```text
uv run python -m app.schema_inventory ../dump_full.sql --output docs/schema-inventory.json
```

The command streams the dump as text and compares table/column names with model
metadata. It does not execute SQL. The tracked JSON is a reconciliation baseline,
not a type/constraint compatibility check. Missing timestamps, polymorphic action
fields, and unmodeled legacy tables must be mapped explicitly before import.

## Optional dump conversion

`app.import_dump` is a deliberately opt-in converter for a **new disposable
SQLite file**. It parses only `INSERT` data, never executes SQL from the dump,
skips Laravel/framework bookkeeping, preserves raw source rows in the target's
`legacy_import_rows` archive, and converts MySQL zero dates to `NULL` where the
target model permits it. The source dump is never changed.

Example dry run (the target and report paths must not already exist):

```text
uv run python -m app.import_dump ../dump_full.sql --target ../data/dump-test.db --dry-run --limit 100 --report ../data/dump-test.json
```

Remove `--dry-run` only for a disposable import. The converter currently accepts
SQLite targets only, refuses non-empty target tables, rejects unsupported
polymorphic action types and malformed/required-field-missing rows, and reports
skipped framework rows. It is not yet an approved production import or MySQL

To audit the full dump without creating a database or importing rows:

```text
uv run python -m app.reconcile_dump ../dump_full.sql --output docs/dump-reconciliation.json
```

The audit counts INSERT rows, reports framework exclusions and empty tables,
lists model foreign keys, records conversion rules, and confirms that the source
was not modified. It does not prove that imported data has valid relationships
or that SQLite constraints/indexes match MariaDB behavior.

To validate an imported disposable SQLite file:

```text
uv run python -m app.validate_import ../data/dump-import.db --output docs/import-validation.json
```

The validator reports foreign-key/orphan summaries, required-field NULLs,
uniqueness violations, date/decimal conversion anomalies, and preserved
validator reports those records and never repairs them automatically. The
selected historical policy preserves all source rows and IDs, creates no
tombstone parents, deletes no orphan rows, archives raw source rows, and does
not claim strict relational validity for historical orphans.

To audit imported domain data without modifying it:

```text
uv run python -m app.historical_audit ../data/dump-import.db --output docs/historical-audit.json
```

The audit covers identity, references, pricing, orders, calculations, bills,
payments, payroll, and report catalogs. It treats empty historical calculation
details as a reported state and rejects no rows.
validator reports those records and never repairs them automatically.
Browser CSRF policy: every state-changing request after the browser has
obtained the `typography_csrf` cookie must carry the matching cookie and
`X-CSRF-Token` header. Stateless compatibility callers that never obtain the
CSRF cookie remain outside this browser contract; a future strict API policy
must use a separate API authentication strategy.
they must use a separate API authentication strategy before being treated as
cookie-authenticated clients.

## Reports — initial implementation slice

To compare a legacy-generated artifact with a rework artifact without modifying
either file:

```text
uv run python -m app.compare_reports legacy.xls rework.xls --output comparison.json
```

The comparator supports PDF and BIFF8 XLS files and reports byte hashes,
extractable PDF text, XLS cell/merge snapshots, and explicit `not_checked`
states for visual acceptance and formulas/print settings. A successful content
comparison is not a substitute for browser or print-layout acceptance.

Report/parameter models mirror the deployed dump schema. `/options/reports`
provides settings and scoped variable editing; APIs are under `/api/report-settings`.
Settings require the report-options permission; original controller omissions
are not reproduced. Model-scoped report discovery uses
`/api/reports/for/{orders|bills}/{id}`, reporting status blocks and renderer
availability rather than supplying broken export links.

The first renderer is IPC `order_transcript`, kind HTML, at the original URL
`/reports/order_transcript/item/{id}`. It reads stored calculation details only
(no implicit recalculation), safely decodes scalar PHP arrays with depth/size/node
limits, and escapes a print_r-style presentation. Earlier JSON calculation data
is accepted as a compatibility fallback. PHP objects/references are rejected.
The output uses the legacy transcript's Arial/8pt base and 1.5em preformatted text;
print_r whitespace and exact browser layout still need comparison.

Vite and Nginx proxy `/reports/` to FastAPI. Download requests use safe ASCII
filenames; responses are no-store/nosniff. Definitions/variables are not invented
or auto-imported: fresh SQLite report catalogs remain empty until populated.

Not yet implemented: PDF rendering, XLS layout/parser/export, order-type variants,
report input forms, passport/economy/design/payment/shipping templates, and payroll
reports. Unsupported generation returns 501 and discovery marks it unavailable.
The bill's "Документы по заказам" action opens passport/economy reports for linked
orders in legacy; it remains deferred until those two formats/templates actually
work, rather than opening broken or substitute documents. HTML-enabled variables
currently use a text editor, not CKEditor. Exact output, seed/import handling,
browser testing and real-data acceptance remain pending.

## Accounting handoff

The standalone payer/bill/payment implementation is closed. Bill detail includes
active linked-order totals and active-payment totals separately from manual paid
flags. Read-only bill views offer an edit action but do not expose payment mutation
buttons; the editor saves before payment navigation. Money displays use two
decimal places. Malformed/reversed date filters return validation errors without
overwriting the previous session filter.

The customer_payer pivot and bidirectional model relationships are retained for
data compatibility. An audit of legacy controllers/views found no editor or
mutation workflow for that relationship; no new association editor was added.

Not completed here: report buttons, exports, and opening order documents from a
bill. Those require the Reports engine and are not replaced with inert actions.
Browser/E2E/visual acceptance, representative dump-backed comparisons, complete
database migration/import, and shared CSRF/session hardening remain project
acceptance work. Internal notes track deviations separately from this handoff.

## Orders–Accounting navigation integration

The Orders editor uses a single bill selector backed by the existing bill search
API. Input is debounced 250 ms, requires one character, cancels stale requests,
and preserves the selected bill independently of search text. Clearing selection
persists an unassigned bill. Manager selection now maps to the update API's
`user_id` field. Save failures retain form input rather than reloading it.

Orders and bill editors honor same-origin application `destination` URLs after
save/cancel. List edit links carry their current list query, and the lists reload
their query parameters. External/malformed destinations fall back to their list;
arbitrary legacy redirects are deliberately not reproduced. The native search
results control replaces Select2, so keyboard/visual browser acceptance is still
required. Tests cover persistence and navigation helpers, not browser clicks.

## Accounting — nested payments

Payments now support submission-based create/edit, confirmation, soft deletion,
restore and permanent deletion under `/accounting/bills/{id}/payments/...`.
APIs mirror that hierarchy under `/api`, with `/form` supplying creation defaults.
Dates accept ISO/DD.MM.YYYY, amounts retain decimal(10,2) precision, and every
request verifies the parent bill. Writes require bill-edit permission; restore
and permanent deletion additionally require their shared permissions.

Payment create/update returns to the bill editor. Cancel/delete/restore returns
to bill detail. Opening payment creation/edit from the bill editor first saves
the bill; failed saves retain inputs and block navigation. Deleted payments are
visible only with trash permission and never contribute to active payment sums.
Manual paid/closed/filed flags are not inferred from payment amounts.

Creation/update under deleted bills is rejected. Payment screens use native
calendar selection with Russian text dates instead of old datepicker plugins.
Browser save/navigation acceptance, Reports integration, Orders bill-search
selector integration, and general CSRF/session hardening remain outstanding.

## Accounting — bills slice

`/accounting/bills` supports sorting/pagination and session-persisted number,
manager, payer, and date-range filters. Create/edit/view/confirmation/restore
routes retain the legacy URL structure; view is read-only, unlike edit.
APIs use `/api/accounting/bills`, `/form`, `/filter`, `/search`, `/{id}`, and
`/{id}/restore`. Search preserves the zero/unselected option and matches all
tokens across bill number, manager names, and payer title (20 results maximum).

Bill fields include date/number, amount/currency, manager/payer, and manual
paid/closed/filed flags. Active payment sums are separate from those flags;
detail includes linked active orders and payments. Dates accept ISO and Russian
DD.MM.YYYY formats; amounts retain two-decimal precision. Read/write permissions
are enforced on APIs rather than reproducing controller omissions. Existing
SQLite bills receive additive columns without dropping records.

Payments are currently summary-only. Payment mutations, report actions, complete
save-and-open-payment/destination behavior, order bill-selector integration and
browser/visual acceptance remain subsequent Accounting work.

## Accounting — payer slice

Payers have list/create/edit/confirmation/restore screens at `/accounting/payers`.
APIs use `/api/accounting/payers` (GET/POST), `/form` (GET), `/{id}`
(GET/PATCH/DELETE), and `/{id}/restore` (POST). Forms save on submission, with
no draft side effect. Original payer_* field names and normalized JSON fields
are accepted. INN remains text, commission uses stored small-integer precision.
Lists sort by ID/name/commission and default to 30 rows, ID descending.
Trash visibility, restore, and permanent-delete permissions are enforced.
Bills, nested payments, bill filters/search, order links and reports remain the
next Accounting slices. SQLite stays the local database; no dump import occurs.

## References implementation handoff

The implemented legacy reference directories now include paper types/formats,
measures, paper inventory/materials, printers and nested fields/processes/stages,
afterprint definitions/stages/materials, compilation definitions/stages/materials,
prepress/redaction, customers/groups, and employee accounts. This closes the
current reference implementation inventory, not full project acceptance.

Employee screens use `/references/users` and create/edit/delete/restore suffixes.
APIs use `/api/employee-references` (GET/POST), `/form` (GET), `/{id}`
(GET/PATCH/DELETE), `/{id}/restore` (POST). Roles are assigned from existing rows;
role/permission administration remains in Settings. Creation requires
`user_create`; edits require `user_edit` on the API, not just the screen.
Surname/name/phone/email/post/role are required. Passwords require matching
confirmation, six characters minimum, and bcrypt's 72-byte maximum. Blank or
unrequested passwords never overwrite hashes. API responses never expose hashes.
Fired and soft-deleted rows are visually distinguished; login/session lookup
excludes soft-deleted accounts. Existing fired-account restrictions are retained.
SQLite upgrades add employee columns without resetting user rows or passwords.

Left behind for cross-project acceptance: shared CSRF/session work; complete
database import/versioning; representative dump-backed comparisons; exact
embedded/modal/widget layout and browser tests; accounting payer associations;
and report-consumer compatibility. Contact CRUD is intentionally not added
because its legacy controller is empty. Service/rate configuration and global
options are tracked with Settings/pricing integration, not invented reference
routes. These boundaries should not be counted as verified production parity.

## Customer references

Customers now have listing/sorting/pagination, submission-based creation,
editing, confirmation, soft deletion, restore and permanent-delete actions at
`/references/customers`. Fields mirror the legacy forms: name, group, phone,
INN (kept as text), address, description. Customer groups use the existing
dictionary screens at `/options/customer-group`, including persisted blank
draft creation. Active groups populate the customer selector; no group maps
to NULL. Server validation respects schema lengths and active group references.

Customer APIs are under `/api/customer-references` (GET/POST), `/form` (GET),
`/{id}` (GET/PATCH/DELETE), and `/{id}/restore` (POST). They integrate with the
existing customer table used by Orders. SQLite startup adds missing columns
without dropping rows; tests cover repeated upgrade and row preservation.

The legacy CustomerContactController is entirely empty and its customer views
contain no contact-management forms; no new contact CRUD was invented. Payer
associations belong to the later accounting slice. Customer confirmations use
dedicated screens instead of modal variants. Exact browser visual acceptance,
CSRF/session hardening, and dump-backed comparisons remain project-level work.
Employees/user-role management remains the next reference implementation slice.

## Prepress/redaction references

The name-only directories are available at `/references/prepresses` and
`/references/redactions`, with create, edit, delete-confirmation, and restore
browser routes. Both save on submission; opening/cancelling a new form does not
create a draft. Lists preserve ID/name sorting, ID-descending defaults and
30-row pagination. Browser sort/page query parameters survive reloads.

Their APIs use `/api/reference-works/{prepresses|redactions}` for GET/POST,
`/{id}` for GET/PATCH/DELETE and `/{id}/restore` for POST. Original form field
names (`prepress_title`, `redaction_title`) are accepted. Titles are required and
limited to the stored 50-character schema. Trash visibility, restore and
permanent deletion use the shared permissions; deleted rows cannot be updated.
The legacy reference views have no pricing links, so pricing stays accessible
through the existing pricing catalog rather than adding new reference actions.
Calculations and prices are unchanged. Browser visual acceptance, shared CSRF,
and dump-backed data validation remain project-level tasks.

## Compilation references

`/references/compiles` now supports definition lists, submission-based creation,
editing, confirmation, soft deletion, restoration, and permanent deletion.
Definitions contain title, fitting-sheet allowance, and four production flags.
Nested stages/materials retain the legacy hierarchy and are saved on submission.
Stages have together, waste, fitting and automatic next ordering weight, without
afterprint-specific density bounds. Material choices use overlapping production
flags; assignment quantities preserve four decimal places.

APIs mirror that hierarchy under `/api/references/compiles`; GET `/stages/form`
and `/materials/form` provide form defaults/options without creating draft rows.
All child requests verify parent ownership, trash visibility, and lifecycle
permissions. Definition titles are bounded to the stored schema length; fitting
and stage values are validated instead of accepting malformed data.
Definition and stage price-history links use `/prices/compile/{id}` and
`/prices/compiles/{id}` respectively. Calculation formulas are unchanged.

Remaining acceptance work: browser/visual and dump-backed comparisons, shared
CSRF/session hardening, and modal/widget appearance. Dedicated confirmations
replace the legacy stage/material modal variants.

## Afterprint references

`/references/afterprints` now lists pre-seeded definitions with sorting and
pagination. Definition editors update title/tooltip and show parameters and
select values read-only: the original route set has no definition create/delete
or parameter/value management actions, so those were not invented.

Nested stage and stage-material screens retain the original create/edit/delete/
restore URL hierarchy under `/references/afterprints/{id}/stages/{stage_id}`.
Both are saved on submission (no drafts). Stages receive the next active weight;
blank/zero maximum density is stored as NULL. Material options are filtered by
overlapping production flags and quantities retain four-decimal precision.
Parent ownership, trash visibility, restoration and permanent-delete permissions
are checked. Pricing-history links use the existing pricing module.

SQLite startup adds missing afterprint production flags/ordering columns without
dropping rows. New local databases contain no invented seeded definitions;
reference population/import remains part of the general data migration.
Dedicated confirmation screens replace legacy modal variants. Browser visual
acceptance and dump-backed integration remain pending. Calculation formulas
are unchanged by this reference-management slice.

## Printer child references

Printer fields, processes, and process stages now have scoped list, create,
detail, update, soft-delete, restore, and permanent-delete APIs. Browser paths
retain the `/references/printers/{id}/fields`, `/processes`, and
`/processes/{process_id}/stages` hierarchy with create/edit/delete/restore suffixes.
The API adds `/items` for child lists and `/form` for input metadata.

Fields are saved on submission, with active paper-format selection, positive
cutting count, field dimensions, and dimensions after cutting. Processes create
blank drafts with 1/0 colors, zero rejection and resolution. Stages create blank
drafts with together=1, colors=1, waste=0, and the next active ordering weight.
Deleted children require `view_trashed`; restore and permanent deletion require
their respective permissions. Every request validates parent ownership.

Dedicated child screens are linked from the printer editor; process screens
link to stage management, and stage lists link to price history when permitted.
The legacy embedded child-table layout/modal variants are not yet reproduced
exactly. Negative values, oversized names, and malformed numbers are subject to
schema-aware validation rather than legacy crashes. Zero together/color values
remain accepted; the existing calculator's safeguards still apply.
Pricing formulas and existing order calculations are unchanged by this slice.

## Reference dictionaries (first references slice)

Implemented paper types, paper formats, and measures at the original browser
paths `/options/paper-type`, `/options/paper-format`, and `/options/measures`.
Create/edit/delete-confirmation/restore screens use their legacy URL suffixes.
Paper types/formats create a persisted blank draft before editing; measures are
inserted only after submitting the new form. Cancelling a draft does not remove it.

Their APIs use `/api/options/{kind}` (GET list, POST store),
`/api/options/{kind}/create` (POST draft/form defaults),
`/api/options/{kind}/{id}` (GET, PATCH, DELETE), and
`/api/options/{kind}/{id}/restore` (POST). Lists default to ID descending and 30
rows per page; deleted entries require `view_trashed`, restoration requires
`restore_trashed`, and deleting an already deleted row requires `delete_trashed`.
Mutations require authentication, matching these legacy controllers. Broader
CSRF hardening is still tracked at the project level.

The measure abbreviation sort uses its actual `short` column, rather than the
legacy model's erroneous `width` column. Abbreviations are rendered as escaped
text rather than executable HTML. Paper-format dimensions are validated as
integers to match the stored schema. Exact browser visual acceptance is pending.

Not included in this slice: paper inventory, materials, printers/fields/processes/
stages, production-work definitions, customer directories, or employee management.

## Reference inventory (second references slice)

Paper inventory and materials are now available at `/references/paper` and
`/references/materials`. Their APIs are under `/api/references/paper` and
`/api/references/materials`, with detail, update, delete, and restore endpoints.
Paper creation saves a draft from the first active type/format (80 gsm, markup
10); missing prerequisites produce a validation response rather than a crash.
Paper names are generated from type, density, and format. Materials include
measure, work type, description, and production flags. Material filters persist
in the session and can be reset. Lists support sorting and pagination.

Startup adds missing inventory columns to existing SQLite tables without
dropping rows. Tests cover repeatable upgrades, paper drafts, generated titles,
material validation/flags, and persisted filter reset.

Remaining inventory acceptance work: legacy create/edit/delete browser URL
flows (the current inventory editor is inline), permission-controlled lifecycle
buttons/permanent deletion UI, complete network-error handling, visual/browser
testing, and dump-backed integration. Printer and production-definition CRUD
remain subsequent references slices. Pricing/calculation behavior is unchanged.

## Database modes

The default local database is SQLite:

```text
DATABASE_URL=sqlite:///./typography.db
```

The `.db` file is created in the backend working directory and is ignored by Git. The old MySQL dump is intentionally not imported or tested locally.

To use MySQL later, set a complete SQLAlchemy URL instead:

```text
DATABASE_URL=mysql+pymysql://typography:typography@mysql:3306/typography
```

The MySQL service is included in the repository Compose file but is disabled by default. When Docker is available, start it with the `mysql` profile and set `DATABASE_URL` to the URL above.

## Local development

```text
uv sync
uv run uvicorn app.main:app --reload
```

The ported foundation exposes `GET /health` and `GET /api/system/database`. Legacy routes and behavior will be ported incrementally from the application under `C:\Dev\legacy-tarasov`.

## Blank calculation

`POST /api/orders/{order_id}/blanks/{blank_id}/recalculate` calculates and
persists the blank cost using its parent order's quantity/date and the stored
paper/material unit price. Its response includes separate `paper`, `print`,
`afterprint`, and `imagesetter` costs and a calculation breakdown. Missing prices
remain zero, as in the legacy application, and are identified in `missing`.

The compatibility implementation intentionally preserves two PHP behaviors:
currency conversion uses the current exchange rate even for historical prices;
afterprint material costs appear in the breakdown but are not added to the
returned stage subtotal. Order aggregation and markups are handled by the
separate order recalculation endpoint.

Run repeatable tests without modifying the working SQLite database:

```text
uv run python -m unittest discover -s tests -v
```

Tests create and dispose of their own in-memory SQLite databases.

Startup applies additive local SQLite compatibility changes before creating
missing tables. This currently includes the legacy `compiles.fitting` column;
no existing local data is dropped.

## Order calculation

`POST /api/orders/{order_id}/recalculate` aggregates blank, prepress, and
redaction costs and applies active order markups without overwriting the stored
sale total. Prepress/redaction follow the legacy `price()` defaults: current
effective date and quantity threshold zero, multiplied by the operation quantity.
Their stored `price_id` and the order date do not select the price.
`work_details` contains line-item breakdowns; missing prices are zero and
reported in `missing`. Compilation uses its current threshold-zero price and
cumulatively adds each work's fitting quantity before calculating blanks.
Compilation-stage waste/material quantities are included in the breakdown;
stage prices and material costs are not added to the returned compilation cost,
matching the original PHP calculation. Material prices use the order date and
material quantity. `production_printing` reports the adjusted quantity without
changing the saved order quantity. Other-work pricing reads its assigned
`price_id` directly, converts at the current exchange rate, and multiplies by
quantity; it does not apply effective-date or quantity-tier selection. A missing
assigned price returns a zero diagnostic line and `missing_prices`, not a
substitute price. All component categories are now wired into aggregation;
`calculated` means no missing prices were detected, not complete UI/import parity.
Order recalculation persists scalar PHP-serialized arrays in `orders.calc_details`
without changing the stored sale total. The top-level keys mirror the legacy
details: printing, design, redaction, compile, other_works, blanks, and markups.
UTF-8 string lengths are encoded in bytes. Existing dump values are not rewritten
until recalculation. Nested breakdown/report compatibility still needs validation
against each report consumer. Startup adds the column to older local SQLite
schemas without dropping data.

## Price management

The frontend exposes `/prices/{kind}` catalogs and `/prices/{kind}/{id}` price
history lists. Separate `/create`, `/{price_id}/edit`, and `/{price_id}/delete`
screens mirror legacy navigation. Create immediately saves a default zero-valued
row; cancel leaves it in place. Saving with `from=list` returns to the catalog;
cancel and delete return to the item's history. `/prices/{kind}/recalculate`
redirects to the catalog without changing prices, just as in the old controller.
Catalogs show the current threshold-zero RUB price. Kinds mirror PriceController: services, paper, print, materials,
afterprint, prepress, redaction, compile, and compiles.

API routes:

- `GET /api/pricing/catalog/{kind}` — reference entries, 50 per page.
- `GET /api/prices/{kind}/{id}/records` — sorted, paginated price records.
- `POST /api/prices/{kind}/{id}/records` — create a validated price.
- `PATCH /api/prices/{kind}/{id}/records/{price_id}` — update a price.
- `DELETE /api/prices/{kind}/{id}/records/{price_id}` — permanent price deletion,
  matching the PHP Price model's lack of SoftDeletes.

The legacy service catalog is initialized with the confirmed `Фотовывод`
service and exposed through `prices/services`. Exchange rates are initialized
from the legacy rate seeder and are used internally by price conversion; the
legacy application exposes no rate-management route or view, so no new CRUD
screen is introduced.

Writes require `edit_price`; deletion requires `delete_price`. The original
controller checks these permissions for action visibility/confirmation but does
not consistently enforce them on writes; the API currently enforces them.
This deliberate hardening is retained with user approval; legacy authorization
omissions are not reproduced.

The order page includes a recalculation button, markup summary, component tables,
compilation materials, and blank stage/material breakdowns. Stage catalogs include
parent printer/process or afterprint/compilation labels. The editor accepts
DD.MM.YYYY dates, provides native calendar selection and bounded quantity buttons
(step 10, range 0–10000), preserves validation input, and disables duplicate saves.
Native controls replace the old calendar/TouchSpin plugins; hold acceleration
and pixel-identical plugin appearance are intentionally not reproduced.

## Pricing handoff status

The pricing implementation scope is closed: catalogs/history, CRUD, confirmation,
permissions, component calculations, persistence, breakdown UI, and regression
tests are implemented. This is not a claim of production acceptance. Cross-project
work left behind:

- CSRF/session hardening across all mutation APIs.
- Representative dump-backed comparisons against PHP outputs (the dump has been
  inspected, not imported or executed locally).
- Full nested calculation/report payload compatibility as report migration proceeds.
- Browser/end-to-end and visual acceptance across the application.
- General migration/versioning and complete reference CRUD, outside pricing.

Validation commands (no Docker, no working database reset):

```text
uv run python -m unittest discover -s tests -q
```

In the frontend module run `npm test` and `npm run build`. Frontend helper tests
exercise dates, quantity boundaries, and error messages; they are not browser tests.
