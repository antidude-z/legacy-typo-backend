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
