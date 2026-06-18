"""Supabase service-role client singleton. Scripts bypass RLS to write."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def get_client() -> Any:
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]  # service role (SUPABASE_KEY shorthand)
    return create_client(url, key)
