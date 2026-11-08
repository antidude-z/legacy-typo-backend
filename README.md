# Typography backend

FastAPI compatibility backend for the legacy typography application.

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
