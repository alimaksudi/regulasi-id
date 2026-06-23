"""Sector x regulation-type matrix and JDIH URL builders.

The JDIH listing is a client-side DataTable: the rows come from a JSON endpoint
(ListDataPeraturan), not the listing HTML. Each row carries the detail-page UUID;
the PDF download UUID still has to be read from the detail page.
"""

from __future__ import annotations

from .config import BASE_URL

# sector code -> jdih `sektor` query value
SECTOR_JDIH = {
    "perbankan": "01",
    "pasar-modal": "02",
    "perasuransian": "04",
    "dana-pensiun": "06",
    "iknb": "08",
    "fintech": "10",
}

# regulation type -> jdih `jenisPeraturan` query value
TYPE_JDIH = {
    "UU": "01",
    "PP": "02",
    "PERPRES": "03",
    "POJK": "06",
    "SEOJK": "07",
    "KEOJK": "08",
}

# Types worth crawling per sector by default (OJK instruments).
DEFAULT_TYPES = ["POJK", "SEOJK", "KEOJK"]


def listing_url(sector: str, reg_type: str) -> str:
    """Human-facing listing page (server returns a JS DataTable shell)."""
    return (
        f"{BASE_URL}/Web/ViewPeraturan/Index"
        f"?sektor={SECTOR_JDIH[sector]}&jenisPeraturan={TYPE_JDIH[reg_type]}"
    )


def data_url(sector: str, reg_type: str, lang: str = "id") -> str:
    """JSON endpoint the DataTable loads its rows from. Returns {aaData: [...]}."""
    return (
        f"{BASE_URL}/Web/ViewPeraturan/ListDataPeraturan"
        f"?sektor={SECTOR_JDIH[sector]}&jenisPeraturan={TYPE_JDIH[reg_type]}&sLanguage={lang}"
    )


def detail_url(uuid: str, sektor: str = "00", jenis: str = "00") -> str:
    return f"{BASE_URL}/Web/ViewPeraturan/Detail/{uuid}/{sektor}/{jenis}"


def download_url(uuid: str) -> str:
    return f"{BASE_URL}/Web/ViewPeraturan/DownloadDokumen/{uuid}"
