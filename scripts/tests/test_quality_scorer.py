from scripts.parser.quality_scorer import score_extraction


class N:
    def __init__(self, node_type, content_text=""):
        self.node_type = node_type
        self.content_text = content_text


def test_empty_is_zero():
    assert score_extraction([], 10) == 0.0


def test_full_score():
    nodes = [N("bab"), N("ayat")] + [N("pasal", "x" * 200) for _ in range(10)]
    # 10 pasals -> 1.0; 2000 chars / 10 pages = 200/page -> 1.0; bab + ayat -> 1.0
    assert score_extraction(nodes, 10) == 1.0


def test_low_score_is_flagged():
    nodes = [N("pasal", "x" * 50)]
    score = score_extraction(nodes, 5)
    # pasal 0.1*0.4 + density (10/200=0.05)*0.4 + structure 0 = 0.06
    assert score == 0.06
    assert score < 0.3


def test_density_caps_at_full():
    nodes = [N("pasal", "x" * 100000), N("bab"), N("ayat")]
    assert score_extraction(nodes, 1) <= 1.0
