"""UTC timestamps stored without timezone, matching existing SQL DATETIME columns."""
from datetime import UTC, datetime


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)