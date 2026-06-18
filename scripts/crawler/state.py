"""crawl_jobs table operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .db import get_client
from .models import CrawlJob


def upsert_job(job: dict[str, Any]) -> None:
    # Dedup on source_url (crawl_jobs has UNIQUE(source_url)).
    get_client().table("crawl_jobs").upsert(
        job, on_conflict="source_url", ignore_duplicates=True
    ).execute()


def claim_jobs(batch_size: int = 10, worker_id: str | None = None) -> list[CrawlJob]:
    res = get_client().rpc(
        "claim_jobs", {"batch_size": batch_size, "worker_id": worker_id}
    ).execute()
    return [CrawlJob(**row) for row in (res.data or [])]


def update_status(job_id: int, status: str, error: str | None = None) -> None:
    patch: dict[str, Any] = {"status": status, "updated_at": _now()}
    if error is not None:
        patch["error_message"] = error
    get_client().table("crawl_jobs").update(patch).eq("id", job_id).execute()


def update_retry(
    job_id: int, retry_count: int, next_retry_at: datetime, error: str
) -> None:
    get_client().table("crawl_jobs").update(
        {
            "status": "failed",
            "retry_count": retry_count,
            "next_retry_at": next_retry_at.isoformat(),
            "error_message": error,
            "updated_at": _now(),
        }
    ).eq("id", job_id).execute()


def mark_loaded(job_id: int, work_id: int, quality: float) -> None:
    get_client().table("crawl_jobs").update(
        {
            "status": "loaded",
            "work_id": work_id,
            "extraction_quality": quality,
            "updated_at": _now(),
        }
    ).eq("id", job_id).execute()


def get_work_updated_at(work_id: int) -> str | None:
    res = (
        get_client()
        .table("works")
        .select("updated_at")
        .eq("id", work_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0]["updated_at"] if rows else None


def _now() -> str:
    from datetime import UTC, datetime as dt

    return dt.now(UTC).isoformat()
