"""Pipeline CLI. Run from project root, e.g.

    python -m scripts.worker.run discover --sectors perbankan,fintech
    python -m scripts.worker.run process --batch-size 20 --concurrency 5
"""

from __future__ import annotations

import asyncio

import typer

app = typer.Typer(help="regulasi-id data pipeline", no_args_is_help=True)


def _sectors(value: str) -> list[str]:
    return [s.strip() for s in value.split(",") if s.strip()]


@app.command()
def discover(
    sectors: str = typer.Option(..., help="comma-separated sector codes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Crawl listing pages and seed crawl_jobs."""
    from .discover import discover as run_discover

    count = asyncio.run(run_discover(_sectors(sectors), dry_run=dry_run))
    typer.echo(f"seeded {count} jobs")


@app.command()
def process(
    batch_size: int = 20,
    concurrency: int = 5,
    max_runtime: int = typer.Option(0, "--max-runtime", help="seconds, 0 = single batch"),
) -> None:
    """Claim and process a batch (download, parse, score, load)."""
    import time

    from ..crawler import state
    from .process import process_batch

    deadline = time.monotonic() + max_runtime if max_runtime else None
    total = 0
    while True:
        jobs = state.claim_jobs(batch_size=batch_size)
        if not jobs:
            break
        asyncio.run(process_batch(jobs, concurrency=concurrency))
        total += len(jobs)
        if deadline is None or time.monotonic() >= deadline:
            break
    typer.echo(f"processed {total} jobs")


@app.command()
def full(sectors: str = typer.Option(...), concurrency: int = 5) -> None:
    """Discover then process in one command."""
    from ..crawler import state
    from .discover import discover as run_discover
    from .process import process_batch

    seeded = asyncio.run(run_discover(_sectors(sectors)))
    typer.echo(f"seeded {seeded} jobs, processing...")
    while True:
        jobs = state.claim_jobs(batch_size=20)
        if not jobs:
            break
        asyncio.run(process_batch(jobs, concurrency=concurrency))


@app.command()
def continuous(discovery_first: bool = typer.Option(False, "--discovery-first")) -> None:
    """Long-running loop for the Railway worker service."""
    import time

    from ..crawler import source_registry, state
    from .discover import discover as run_discover
    from .process import process_batch

    if discovery_first:
        asyncio.run(run_discover(list(source_registry.SECTOR_JDIH.keys())))
    while True:
        jobs = state.claim_jobs(batch_size=20)
        if jobs:
            asyncio.run(process_batch(jobs))
        else:
            time.sleep(30)


@app.command()
def embed(batch_size: int = 100) -> None:
    """Generate embeddings for nodes where embedding IS NULL."""
    from ..embeddings.generate import generate_embeddings

    asyncio.run(generate_embeddings(batch_size=batch_size))


@app.command()
def retry(limit: int = 100) -> None:
    """Process failed jobs whose backoff has elapsed (claim_jobs picks them up)."""
    from ..crawler import state
    from .process import process_batch

    jobs = state.claim_jobs(batch_size=limit)
    asyncio.run(process_batch(jobs))
    typer.echo(f"retried {len(jobs)} jobs")


@app.command(name="reset-dead")
def reset_dead(sector: str = typer.Option(None, help="limit to one sector")) -> None:
    """Reset dead-letter jobs back to pending."""
    from ..crawler.db import get_client

    q = (
        get_client()
        .table("crawl_jobs")
        .update({"status": "pending", "retry_count": 0, "next_retry_at": None})
        .eq("status", "dead")
    )
    if sector:
        q = q.eq("sector_code", sector)
    q.execute()
    typer.echo("dead jobs reset to pending")


@app.command()
def stats() -> None:
    """Job counts by status and embedding coverage."""
    from ..crawler.db import get_client

    sb = get_client()
    statuses = [
        "pending", "crawling", "downloaded", "parsed",
        "loaded", "flagged", "failed", "dead", "skipped",
    ]
    for s in statuses:
        res = sb.table("crawl_jobs").select("id", count="exact", head=True).eq("status", s).execute()
        typer.echo(f"{s:>11}: {res.count or 0}")
    works = sb.table("works").select("id", count="exact", head=True).execute()
    typer.echo(f"{'works':>11}: {works.count or 0}")


if __name__ == "__main__":
    app()
