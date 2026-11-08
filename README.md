# Typography backend

FastAPI compatibility backend for the legacy typography application.

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
Calculation-detail persistence and frontend integration remain pending.
