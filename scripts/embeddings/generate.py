"""Incremental embedding generation. Only touches nodes with embedding IS NULL."""

from __future__ import annotations

import structlog

from ..crawler.db import get_client

log = structlog.get_logger()

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536


def _fetch_nodes_without_embeddings(limit: int) -> list[dict]:
    res = (
        get_client()
        .table("document_nodes")
        .select("id, node_type, number, content_text")
        .is_("embedding", "null")
        .not_.is_("content_text", "null")
        .limit(limit)
        .execute()
    )
    return res.data or []


def _update_embedding(node_id: int, embedding: list[float]) -> None:
    get_client().table("document_nodes").update({"embedding": embedding}).eq(
        "id", node_id
    ).execute()


async def generate_embeddings(batch_size: int = 100) -> None:
    import openai

    client = openai.AsyncOpenAI()  # OPENAI_API_KEY from env
    total = 0
    while True:
        nodes = _fetch_nodes_without_embeddings(batch_size)
        if not nodes:
            break

        texts = [
            f"{n['node_type']} {n.get('number') or ''}\n{n.get('content_text') or ''}"
            for n in nodes
        ]
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL, input=texts, dimensions=EMBEDDING_DIMS
        )
        embeddings = [e.embedding for e in response.data]

        for node, embedding in zip(nodes, embeddings):
            _update_embedding(node["id"], embedding)

        total += len(nodes)
        log.info("embeddings_generated", count=len(nodes), total=total)
