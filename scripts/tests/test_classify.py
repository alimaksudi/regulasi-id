from scripts.parser.classify_pdf import classify


def test_born_digital():
    assert classify("x" * 300, 1) == "born_digital"


def test_scanned_clean():
    assert classify("x" * 50, 1) == "scanned_clean"


def test_image_only():
    assert classify("   ", 1) == "image_only"


def test_uses_per_page_density():
    # 600 chars over 4 pages = 150/page -> scanned_clean (below 200 born-digital cutoff)
    assert classify("x" * 600, 4) == "scanned_clean"
