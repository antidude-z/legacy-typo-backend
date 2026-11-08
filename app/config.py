import os
from pathlib import Path


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/typography.db")
DATABASE_MODE = "mysql" if DATABASE_URL.startswith(("mysql://", "mysql+")) else "sqlite"
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-change-me")
SESSION_COOKIE = os.getenv("SESSION_COOKIE", "laravel_session")
RESET_MAIL_MODE = os.getenv("RESET_MAIL_MODE", "disabled")
RESET_MAIL_DIR = Path(os.getenv("RESET_MAIL_DIR", "./data/mail"))
RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "60"))
REMEMBER_DAYS = int(os.getenv("REMEMBER_DAYS", "30"))
SESSION_SECURE = os.getenv("SESSION_SECURE", "false").lower() == "true"
APP_URL = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
