"""Sector x regulation-type matrix and JDIH URL builders.

Detail page UUID (in the URL) is NOT the PDF download UUID (in the page HTML).
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
    return (
        f"{BASE_URL}/Web/ViewPeraturan/Index"
        f"?sektor={SECTOR_JDIH[sector]}&jenisPeraturan={TYPE_JDIH[reg_type]}"
    )


def detail_url(uuid: str) -> str:
    return f"{BASE_URL}/web/ViewPeraturan/Detail/{uuid}/00/00"


def download_url(uuid: str) -> str:
    return f"{BASE_URL}/Web/ViewPeraturan/DownloadDokumen/{uuid}"
