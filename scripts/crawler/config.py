"""HTTP client config for the JDIH crawler. This is a government server: be polite."""

from __future__ import annotations

BASE_URL = "http://jdih.ojk.go.id"

# 1 to 2 seconds between requests (SCRAPER.md gotcha).
REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 60.0

# Concurrent downloads within the process pool (asyncio.Semaphore).
DOWNLOAD_CONCURRENCY = 5

HEADERS = {
    "User-Agent": "regulasi-id-crawler/1.0 (+https://regulasi.id)",
    "Accept-Language": "id-ID,id;q=0.9",
}

# OJK PDFs occasionally have certificate issues; verification can be toggled per env.
VERIFY_SSL = True

# Quality below this is flagged for admin review instead of loaded.
QUALITY_FLAG_THRESHOLD = 0.3
