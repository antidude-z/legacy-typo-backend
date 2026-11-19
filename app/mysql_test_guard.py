"""Safeguards for opt-in destructive MySQL integration tests."""
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DATABASES = frozenset({'typography_runtime_test', 'typography_imported_test', 'typography_fullclone_test'})


def validate_test_url(url: str, working_url: str | None = None) -> None:
    target = make_url(url)
    if target.get_backend_name() != 'mysql' or target.database not in TEST_DATABASES:
        raise ValueError('Refusing non-dedicated MySQL test database')
    if working_url:
        working = make_url(working_url)
        if (target.host, target.port or 3306, target.database) == (working.host, working.port or 3306, working.database):
            raise ValueError('Test database matches configured working database')


def verify_test_database(url: str, working_url: str | None = None) -> dict:
    validate_test_url(url, working_url)
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            actual = connection.scalar(text('SELECT DATABASE()'))
            if actual != make_url(url).database:
                raise ValueError('Connected database differs from test target')
            return {'database': actual, 'server_version': connection.scalar(text('SELECT VERSION()'))}
    finally:
        engine.dispose()