from scripts.crawler import source_registry as sr


def test_listing_url():
    assert sr.listing_url("perbankan", "POJK") == (
        "http://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=01&jenisPeraturan=06"
    )
    assert sr.listing_url("fintech", "SEOJK") == (
        "http://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=10&jenisPeraturan=07"
    )


def test_detail_and_download_url():
    uuid = "abcdef01-2345-6789-abcd-ef0123456789"
    assert sr.detail_url(uuid) == f"http://jdih.ojk.go.id/web/ViewPeraturan/Detail/{uuid}/00/00"
    assert sr.download_url(uuid) == f"http://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/{uuid}"


def test_matrices_cover_all_sectors_and_types():
    assert set(sr.SECTOR_JDIH) == {
        "perbankan", "pasar-modal", "iknb", "fintech", "dana-pensiun", "perasuransian",
    }
    assert set(sr.TYPE_JDIH) == {"UU", "PP", "PERPRES", "POJK", "SEOJK", "KEOJK"}
