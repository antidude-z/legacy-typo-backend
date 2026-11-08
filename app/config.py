import os


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./typography.db")
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-change-me")
SESSION_COOKIE = os.getenv("SESSION_COOKIE", "laravel_session")
