"""Regex state machine turning extracted PDF text into a node tree.

Hierarchy: BAB > Bagian > Paragraf > Pasal > Ayat. Returns a flat list of
ParsedNode with parent_index and depth set, so the loader can insert breadth-first.
"""

from __future__ import annotations

import re

from ..crawler.models import ParsedNode

RE_BAB = re.compile(r"^BAB\s+([IVXLCDM]+)\b", re.IGNORECASE)
RE_BAGIAN = re.compile(r"^Bagian\s+(\w+)", re.IGNORECASE)
RE_PARAGRAF = re.compile(r"^Paragraf\s+(\d+)", re.IGNORECASE)
RE_PASAL = re.compile(r"^Pasal\s+(\d+[A-Za-z]?)\s*$", re.IGNORECASE)
RE_AYAT = re.compile(r"^\((\d+[a-z]?)\)\s*(.*)$")
RE_PAGE = re.compile(r"^\[\[page\s+\d+\]\]$", re.IGNORECASE)


def parse_structure(text: str) -> list[ParsedNode]:
    nodes: list[ParsedNode] = []
    sort = 0

    # Index of the current open node at each level.
    cur = {"bab": None, "bagian": None, "paragraf": None, "pasal": None, "ayat": None}
    # Node currently receiving free-text content lines.
    content_target: int | None = None
    pending_heading_for: int | None = None  # capture next non-empty line as heading

    def add(node_type: str, number: str | None, parent_index: int | None) -> int:
        nonlocal sort
        sort += 100
        depth = 0 if parent_index is None else nodes[parent_index].depth + 1
        nodes.append(
            ParsedNode(
                node_type=node_type,
                number=number,
                sort_order=sort,
                depth=depth,
                parent_index=parent_index,
            )
        )
        return len(nodes) - 1

    def append_content(idx: int, line: str) -> None:
        existing = nodes[idx].content_text
        nodes[idx].content_text = line if existing is None else f"{existing}\n{line}"

    def nearest(*levels: str) -> int | None:
        for level in levels:
            if cur[level] is not None:
                return cur[level]
        return None

    for raw in text.split("\n"):
        line = raw.strip()
        if not line or RE_PAGE.match(line):
            continue

        if pending_heading_for is not None:
            nodes[pending_heading_for].heading = line
            pending_heading_for = None
            continue

        m = RE_BAB.match(line)
        if m:
            idx = add("bab", m.group(1).upper(), None)
            cur.update(bab=idx, bagian=None, paragraf=None, pasal=None, ayat=None)
            content_target = None
            pending_heading_for = idx
            continue

        m = RE_BAGIAN.match(line)
        if m:
            idx = add("bagian", m.group(1), cur["bab"])
            cur.update(bagian=idx, paragraf=None, pasal=None, ayat=None)
            content_target = None
            pending_heading_for = idx
            continue

        m = RE_PARAGRAF.match(line)
        if m:
            idx = add("paragraf", m.group(1), nearest("bagian", "bab"))
            cur.update(paragraf=idx, pasal=None, ayat=None)
            content_target = None
            pending_heading_for = idx
            continue

        m = RE_PASAL.match(line)
        if m:
            idx = add("pasal", m.group(1), nearest("paragraf", "bagian", "bab"))
            cur.update(pasal=idx, ayat=None)
            content_target = idx
            continue

        m = RE_AYAT.match(line)
        if m and cur["pasal"] is not None:
            idx = add("ayat", m.group(1), cur["pasal"])
            cur["ayat"] = idx
            content_target = idx
            if m.group(2):
                append_content(idx, m.group(2))
            continue

        if content_target is not None:
            append_content(content_target, line)

    return nodes
