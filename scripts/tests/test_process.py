from scripts.worker.process import extract_download_uuids


def test_empty_labels_first_link_is_main_pdf():
    # Real JDIH: the download link has no text.
    html = "<a href='/Web/ViewPeraturan/DownloadDokumen/b783d7fb-6abd-f735-e0ce-75535255a05a'></a>"
    out = extract_download_uuids(html)
    assert out["peraturan"] == "b783d7fb-6abd-f735-e0ce-75535255a05a"


def test_labeled_links_classified():
    html = (
        "<a href='/x/DownloadDokumen/11111111-1111-1111-1111-111111111111'>Peraturan</a>"
        "<a href='/x/DownloadDokumen/22222222-2222-2222-2222-222222222222'>Abstrak</a>"
        "<a href='/x/DownloadDokumen/33333333-3333-3333-3333-333333333333'>FAQ</a>"
    )
    out = extract_download_uuids(html)
    assert out["peraturan"] == "11111111-1111-1111-1111-111111111111"
    assert out["abstrak"] == "22222222-2222-2222-2222-222222222222"
    assert out["faq"] == "33333333-3333-3333-3333-333333333333"


def test_no_links():
    assert extract_download_uuids("<p>nothing here</p>") == {}
