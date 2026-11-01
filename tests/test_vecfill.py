"""Missing SPECTER2 rows are encoded once and reused. No index rebuild."""

import numpy as np

from rrm.search.vecfill import fill_encoded, read_cache, slots_from


def test_encode_fills_a_hole_and_the_cache_skips_a_second_call(tmp_path):
    rows = [
        {"corpusid": 1, "title": "Known", "abstract": "already stored"},
        {"corpusid": 2, "title": "Missing title", "abstract": "needs a vector"},
    ]
    stored = [np.ones(4, dtype=np.float32), None]
    calls = []

    def encode(texts):
        calls.append(list(texts))
        return np.asarray([[0.2, 0.3, 0.4, 0.5]], dtype=np.float32)

    slots, missing = slots_from(rows, stored, tmp_path)
    assert missing == [2]
    matrix, still = fill_encoded(rows, slots, encode, tmp_path)
    assert still == []
    assert matrix.shape == (2, 4)
    assert calls == [["Missing title\nneeds a vector"]]
    cached = read_cache(tmp_path, 2)
    assert cached is not None and cached.shape == (4,)

    again, missing_again = slots_from(rows, [stored[0], None], tmp_path)
    assert missing_again == []
    assert again[1] is not None


def test_no_text_stays_missing_and_does_not_invent_a_vector(tmp_path):
    rows = [{"corpusid": 7, "title": "", "abstract": None}]
    slots, missing = slots_from(rows, [None], tmp_path)
    assert missing == [7]
    matrix, still = fill_encoded(rows, slots, lambda texts: (_ for _ in ()).throw(AssertionError("encode")), tmp_path)
    assert matrix is None
    assert still == [7]
