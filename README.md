# Typography backend

FastAPI compatibility backend for the legacy typography application.

## Local development

```text
python -m venv .venv
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The initial scaffold exposes `GET /health`. Legacy routes and behavior will be ported incrementally from the application under `C:\Dev\legacy-tarasov`.
