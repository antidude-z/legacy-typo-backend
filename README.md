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
returned stage subtotal. Full order markups/compilation are not included yet.

Run repeatable tests without modifying the working SQLite database:

```text
uv run python -m unittest discover -s tests -v
```

Tests create and dispose of their own in-memory SQLite databases.
