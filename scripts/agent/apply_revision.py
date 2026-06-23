"""Python wrapper for the apply_revision() SQL function (the only sanctioned
path to mutate node content: audit row + content update + embedding reset)."""

from __future__ import annotations

from ..crawler.db import get_client


def apply_revision(
    node_id: int,
    new_content: str,
    reason: str,
    actor: str,
    suggestion_id: int | None = None,
) -> None:
    get_client().rpc(
        "apply_revision",
        {
            "p_node_id": node_id,
            "p_new_content": new_content,
            "p_reason": reason,
            "p_actor": actor,
            "p_suggestion_id": suggestion_id,
        },
    ).execute()
