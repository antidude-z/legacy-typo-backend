import unittest
from datetime import UTC, datetime

from app.clock import utc_now


class ClockTests(unittest.TestCase):
    def test_storage_clock_is_naive_utc_without_deprecated_calls(self):
        before = datetime.now(UTC).replace(tzinfo=None)
        actual = utc_now()
        after = datetime.now(UTC).replace(tzinfo=None)
        self.assertIsNone(actual.tzinfo)
        self.assertLessEqual(before, actual)
        self.assertLessEqual(actual, after)