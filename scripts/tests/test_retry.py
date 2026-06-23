from datetime import UTC, datetime, timedelta

from scripts.crawler.retry import MAX_RETRIES, is_dead, next_retry_at

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_schedule_deltas():
    assert next_retry_at(1, NOW) - NOW == timedelta(minutes=5)
    assert next_retry_at(2, NOW) - NOW == timedelta(minutes=30)
    assert next_retry_at(3, NOW) - NOW == timedelta(hours=2)
    assert next_retry_at(4, NOW) - NOW == timedelta(hours=8)


def test_dead_after_max():
    assert MAX_RETRIES == 4
    assert is_dead(5) is True
    assert is_dead(4) is False
    assert next_retry_at(5, NOW) is None
