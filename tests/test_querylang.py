"""Idioma de la consulta y el aviso de coseno. Sin descargar el modelo."""

from rrm.search.querylang import (
    TOPIC_COSINE,
    TOPIC_NOTE,
    cache_miss_spanish,
    far_group_ids,
    looks_spanish,
    retrieval_query,
    topic_fields,
)


def test_spanish_questions_are_detected_and_english_ones_are_not():
    assert looks_spanish("¿Cómo funciona la atención en un transformer?")
    assert looks_spanish("¿Por qué el softmax se divide por la raíz de d_k?")
    assert looks_spanish("what learning algorithm is in-context learning") is False
    assert looks_spanish("how do neural radiance fields avoid aliasing") is False
    assert looks_spanish("a survey of graph neural networks for molecules") is False


def test_retrieval_uses_the_translation_and_keeps_english():
    encoded, shown = retrieval_query("¿Cómo funciona?", translate=lambda text: "How does it work?")
    assert encoded == "How does it work?" and shown == "How does it work?"
    encoded, shown = retrieval_query("how do fields avoid aliasing", translate=lambda text: "no")
    assert encoded == "how do fields avoid aliasing" and shown == ""
    encoded, shown = retrieval_query("¿la atención?", translate=lambda text: (_ for _ in ()).throw(RuntimeError("x")))
    assert encoded == "¿la atención?" and shown == "¿la atención?"


def test_old_spanish_cache_is_recomputed():
    assert cache_miss_spanish("¿la atención?", {"papers": []}) is True
    assert cache_miss_spanish("¿la atención?", {"query_en": "attention"}) is False
    assert cache_miss_spanish("attention", {}) is False


def test_low_top_cosine_says_so():
    def cosine(left, right):
        return float(right[0])

    def vector_of(cid):
        return [0.2 if cid == 1 else 0.9]

    low = topic_fields([1.0], [1], vector_of, cosine)
    assert low["topic_cosine"] == 0.2
    assert low["topic_note"] == TOPIC_NOTE
    assert low["topic_cosine"] < TOPIC_COSINE
    high = topic_fields([1.0], [2], vector_of, cosine)
    assert high["topic_cosine"] == 0.9
    assert high["query_cosines"] == {"2": 0.9}
    assert "topic_note" not in high


def test_a_group_is_far_only_against_this_question():
    assert far_group_ids({"a": [0.77, 0.75, 0.74], "b": [0.76, 0.73]}) == []
    assert far_group_ids({"near": [0.76, 0.74], "far": [0.48, 0.44]}) == ["far"]
    assert far_group_ids({"only": [0.4, 0.2]}) == []
    assert far_group_ids({"a": [0.77, 0.76, 0.50], "b": [0.75, 0.74]}) == []
