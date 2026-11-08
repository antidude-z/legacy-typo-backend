# Typography backend

FastAPI compatibility backend for the legacy typography application.

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
