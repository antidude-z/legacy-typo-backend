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
SESSION_MINUTES = int(os.getenv("SESSION_MINUTES", "120"))
LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "5"))
LOGIN_RATE_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "300"))
APP_URL = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
PRODUCTION = os.getenv('APP_ENV', 'development') == 'production'
LOGIN_LIMIT_DB = os.getenv('LOGIN_LIMIT_DB', './data/login-limits.db')


def validate_production_settings(environ=None):
    """Fail closed before connecting to a database in production."""
    from urllib.parse import urlsplit
    values = os.environ if environ is None else environ
    if values.get('APP_ENV') != 'production':
        return
    secret = values.get('SESSION_SECRET', '')
    if len(secret) < 32 or secret in {'development-only-change-me', 'replace-with-a-local-secret'}:
        raise ValueError('Production requires a random SESSION_SECRET of at least 32 characters')
    url = urlsplit(values.get('APP_URL', ''))
    if url.scheme != 'https' or not url.hostname or url.username or url.query or url.fragment:
        raise ValueError('Production APP_URL must be an HTTPS URL without credentials/query/fragment')
    if values.get('SESSION_SECURE', '').lower() != 'true':
        raise ValueError('Production requires SESSION_SECURE=true')
    if values.get('FORWARDED_ALLOW_IPS') == '*':
        raise ValueError('Trust only explicit reverse proxy IPs, not all forwarded headers')
    if values.get('RESET_MAIL_MODE', 'disabled') not in {'disabled', 'smtp'}:
        raise ValueError('Production reset mail must use SMTP or be explicitly disabled')
    if values.get('RESET_MAIL_MODE') == 'smtp':
        if not values.get('MAIL_HOST') or not values.get('MAIL_FROM'):
            raise ValueError('SMTP requires MAIL_HOST and MAIL_FROM')
        if values.get('MAIL_USERNAME') and not values.get('MAIL_PASSWORD'):
            raise ValueError('SMTP username requires a password')
    for name, default in [('SESSION_MINUTES', '120'), ('REMEMBER_DAYS', '30'),
                          ('LOGIN_RATE_LIMIT', '5'), ('LOGIN_RATE_WINDOW_SECONDS', '300')]:
        if int(values.get(name, default)) <= 0:
            raise ValueError(f'{name} must be positive')


validate_production_settings()
