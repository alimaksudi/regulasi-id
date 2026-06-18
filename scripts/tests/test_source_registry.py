from scripts.crawler import source_registry as sr
from scripts.worker.discover import row_to_job


def test_data_url():
    assert sr.data_url("perbankan", "POJK") == (
        "https://jdih.ojk.go.id/Web/ViewPeraturan/ListDataPeraturan"
        "?sektor=01&jenisPeraturan=06&sLanguage=id"
    )
    assert sr.data_url("fintech", "SEOJK") == (
        "https://jdih.ojk.go.id/Web/ViewPeraturan/ListDataPeraturan"
        "?sektor=10&jenisPeraturan=07&sLanguage=id"
    )


def test_detail_and_download_url():
    uuid = "abcdef01-2345-6789-abcd-ef0123456789"
    assert sr.detail_url(uuid, "01", "06") == (
        f"https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/{uuid}/01/06"
    )
    assert sr.download_url(uuid) == (
        f"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/{uuid}"
    )


def test_matrices_cover_all_sectors_and_types():
    assert set(sr.SECTOR_JDIH) == {
        "perbankan", "pasar-modal", "iknb", "fintech", "dana-pensiun", "perasuransian",
    }
    assert set(sr.TYPE_JDIH) == {"UU", "PP", "PERPRES", "POJK", "SEOJK", "KEOJK"}


def test_row_to_job_parses_detail_uuid():
    row = [
        "<a href='https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/"
        "53eb4326-67df-d103-ca6e-c4167419e97d/01/06'>POJK Nomor 9/POJK.03/2016</a>",
        "9", "Perbankan", None, None, "Peraturan OJK", "", "Berlaku",
    ]
    job = row_to_job(row, "perbankan", "POJK")
    assert job["detail_uuid"] == "53eb4326-67df-d103-ca6e-c4167419e97d"
    assert job["source_url"].endswith("/Detail/53eb4326-67df-d103-ca6e-c4167419e97d/01/06")
    assert job["sector_code"] == "perbankan"
    assert job["status"] == "pending"


def test_row_to_job_skips_rows_without_link():
    assert row_to_job(["no link here", "x"], "perbankan", "POJK") is None
    assert row_to_job([], "perbankan", "POJK") is None
