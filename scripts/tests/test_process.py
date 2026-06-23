from scripts.worker.process import extract_download_uuids, select_main_pdf


def test_empty_labels_returns_ordered_uuids():
    # Real JDIH: download links have no text.
    html = (
        "<a href='/x/DownloadDokumen/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'></a>"
        "<a href='/x/DownloadDokumen/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'></a>"
    )
    out = extract_download_uuids(html)
    assert out["ordered"] == [
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    ]
    assert out["labeled"] == {}


def test_labeled_links_classified():
    html = (
        "<a href='/x/DownloadDokumen/11111111-1111-1111-1111-111111111111'>Peraturan</a>"
        "<a href='/x/DownloadDokumen/22222222-2222-2222-2222-222222222222'>Abstrak</a>"
        "<a href='/x/DownloadDokumen/33333333-3333-3333-3333-333333333333'>FAQ</a>"
    )
    out = extract_download_uuids(html)
    assert out["labeled"]["peraturan"] == "11111111-1111-1111-1111-111111111111"
    assert out["labeled"]["abstrak"] == "22222222-2222-2222-2222-222222222222"
    assert out["labeled"]["faq"] == "33333333-3333-3333-3333-333333333333"
    assert len(out["ordered"]) == 3


def test_no_links():
    assert extract_download_uuids("<p>nothing</p>") == {"ordered": [], "labeled": {}}


def test_select_main_pdf_picks_most_pasal():
    # The regulation has many Pasal; the abstract/FAQ have none.
    assert select_main_pdf([("abstract", 0), ("regulation", 52), ("faq", 0)]) == "regulation"
    assert select_main_pdf([]) is None
