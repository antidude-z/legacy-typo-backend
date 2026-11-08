import os


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/typography.db")
DATABASE_MODE = "mysql" if DATABASE_URL.startswith(("mysql://", "mysql+")) else "sqlite"
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-change-me")
SESSION_COOKIE = os.getenv("SESSION_COOKIE", "laravel_session")
