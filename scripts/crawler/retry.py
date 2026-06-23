"""Exponential backoff schedule for failed crawl jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

BACKOFF_SCHEDULE = [
    timedelta(minutes=5),   # retry 1
    timedelta(minutes=30),  # retry 2
    timedelta(hours=2),     # retry 3
    timedelta(hours=8),     # retry 4
]
MAX_RETRIES = len(BACKOFF_SCHEDULE)


def is_dead(retry_count: int) -> bool:
    """A job that has exhausted the schedule goes to the dead-letter state."""
    return retry_count > MAX_RETRIES


def next_retry_at(retry_count: int, now: datetime | None = None) -> datetime | None:
    """When to retry next given the new retry_count (1-based). None means dead."""
    if is_dead(retry_count):
        return None
    now = now or datetime.now(UTC)
    return now + BACKOFF_SCHEDULE[retry_count - 1]
