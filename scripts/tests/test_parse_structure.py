from scripts.parser.parse_structure import parse_structure

SAMPLE = """[[page 1]]
BAB I
KETENTUAN UMUM
Pasal 1
Dalam Peraturan ini yang dimaksud dengan:
(1) Bank adalah badan usaha.
(2) Nasabah adalah pihak.
Pasal 2
Ketentuan lain berlaku.
BAB II
PERIZINAN
Bagian Kesatu
Umum
Pasal 3
Setiap pihak wajib memiliki izin.
"""


def _by_type(nodes, t):
    return [n for n in nodes if n.node_type == t]


def test_counts_and_headings():
    nodes = parse_structure(SAMPLE)
    babs = _by_type(nodes, "bab")
    assert [b.number for b in babs] == ["I", "II"]
    assert [b.heading for b in babs] == ["KETENTUAN UMUM", "PERIZINAN"]
    assert [p.number for p in _by_type(nodes, "pasal")] == ["1", "2", "3"]
    assert [a.number for a in _by_type(nodes, "ayat")] == ["1", "2"]
    bagian = _by_type(nodes, "bagian")
    assert len(bagian) == 1 and bagian[0].heading == "Umum"


def test_hierarchy_links_and_depth():
    nodes = parse_structure(SAMPLE)
    pasal1 = next(n for n in nodes if n.node_type == "pasal" and n.number == "1")
    pasal1_idx = nodes.index(pasal1)
    ayat = [n for n in nodes if n.node_type == "ayat"]
    assert all(a.parent_index == pasal1_idx for a in ayat)
    assert all(a.depth == pasal1.depth + 1 for a in ayat)

    # Pasal 3 sits under Bagian Kesatu, which sits under BAB II.
    pasal3 = next(n for n in nodes if n.node_type == "pasal" and n.number == "3")
    parent = nodes[pasal3.parent_index]
    assert parent.node_type == "bagian"
    assert nodes[parent.parent_index].node_type == "bab"


def test_content_capture():
    nodes = parse_structure(SAMPLE)
    pasal1 = next(n for n in nodes if n.node_type == "pasal" and n.number == "1")
    assert "Dalam Peraturan ini" in (pasal1.content_text or "")
    ayat1 = next(n for n in nodes if n.node_type == "ayat" and n.number == "1")
    assert ayat1.content_text == "Bank adalah badan usaha."


def test_page_markers_ignored():
    nodes = parse_structure(SAMPLE)
    assert all("[[page" not in (n.content_text or "") for n in nodes)
