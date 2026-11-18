"""Static deployment checks that do not require a running Docker daemon."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit


def validate_mysql_url(url: str) -> dict:
    if not url.startswith(("mysql://", "mysql+")):
        raise ValueError("DATABASE_URL must use a MySQL SQLAlchemy dialect")
    parsed = urlsplit(url)
    if not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("MySQL DATABASE_URL must include host and database")
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError("unsupported MySQL SQLAlchemy dialect")
    return {
        "dialect": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "database": parsed.path.strip("/"),
        "has_username": bool(parsed.username),
        "has_password": bool(parsed.password),
    }


def validate_compose(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    required = {
        "backend": "context: ./backend",
        "frontend": "context: ./frontend",
        "mysql": "image: mysql:8.0",
    }
    errors = []
    for service, marker in required.items():
        if marker not in text:
            errors.append(f"missing {service} configuration")
    for marker in (
        "profiles:",
        "- mysql",
        "backend_data:/app/data",
        "mysql_data:/var/lib/mysql",
        '"8000:8000"',
        '"8080:80"',
    ):
        if marker not in text:
            errors.append(f"missing compose marker: {marker}")
    if "DATABASE_URL: ${DATABASE_URL:-sqlite:///./data/typography.db}" not in text:
        errors.append("backend does not expose the SQLite-default DATABASE_URL switch")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "valid": True,
        "services": ["backend", "frontend", "mysql"],
        "mysql_profile": "mysql",
        "default_database": "sqlite",
        "mysql_database": "mysql+pymysql",
        "runtime_verified": False,
    }


def validate_nginx_proxy(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if "proxy_pass http://backend:8000;" not in text:
        raise ValueError("frontend proxy does not target the backend service")
    return {"valid": True, "target": "backend:8000", "paths": ["/api/", "/reports/"]}