"""Survey y retractación con respuestas mock. Sin red real."""

from rrm.reader.files import resolve_figure, resolve_source_pdf
from rrm.search.labelhttp import parse_s2
from rrm.search.labelnet import cosines_for, lookup_meta
from rrm.search.labels import NO_RETRACTION, OFFLINE_NOTE, apply_survey, is_review, label_payload


def test_title_does_not_make_a_preprint_a_review():
    assert is_review(["JournalArticle"], None) is False
    assert is_review([], "article") is False
    assert is_review(["Review"], None) is True
    assert is_review([], "review") is True
    papers = [{"corpusid": 1, "title": "A Review of Everything"}]
    meta = {1: {"publication_types": ["JournalArticle"], "title": papers[0]["title"], "abstract": "x"}}
    out, extra = apply_survey(papers, meta, {1: 0.95})
    assert extra is None and out[0]["survey"] is False


def test_survey_needs_cosine_and_takes_one_slot():
    low = {2: {"publication_types": ["Review"], "abstract": "s", "paper": {"corpusid": 2, "title": "Survey"}}}
    out, extra = apply_survey([{"corpusid": 1, "title": "Other"}], low, {2: 0.2})
    assert extra is None and all(not row.get("survey") for row in out)
    high = {2: {"publication_types": [], "openalex_type": "review", "abstract": "s", "paper": {"corpusid": 2, "title": "Survey"}}}
    out, extra = apply_survey([{"corpusid": 1, "title": "Other"}], high, {2: 0.7})
    assert extra["corpusid"] == 2 and extra["survey"] is True
    assert out[-1]["corpusid"] == 2
    again, extra = apply_survey(out, high, {2: 0.7})
    assert extra is None and sum(1 for row in again if row["survey"]) == 1


def test_lookup_uses_cache_and_marks_retraction(tmp_path):
    calls = {"s2": 0}

    def s2(ids, timeout):
        calls["s2"] += 1
        assert ids == [7] and timeout
        return [{"abstract": "hola", "publicationTypes": ["Review"], "externalIds": {"DOI": "10.1/abc"}, "title": "T", "tldr": {"text": "gen"}}]

    def crossref(doi, timeout):
        assert doi == "10.1/abc"
        return {"update-to": [{"type": "retraction", "source": "retraction-watch"}]}

    found = lookup_meta([7], tmp_path, s2_fetch=s2, crossref_fetch=crossref, openalex_fetch=lambda *_: {})
    assert found[7]["abstract"] == "hola"
    assert found[7]["retracted"] is True
    assert parse_s2({"publicationTypes": ["Review"], "abstract": "hola"} )["publication_types"] == ["Review"]

    def boom(*_args, **_kwargs):
        raise AssertionError("red")

    again = lookup_meta([7], tmp_path, s2_fetch=boom, crossref_fetch=boom, openalex_fetch=lambda *_: {})
    assert again[7]["retracted"] is True and calls["s2"] == 1


def test_missing_retraction_and_offline_note(tmp_path):
    def s2(ids, _timeout):
        return [{"abstract": "", "publicationTypes": [], "externalIds": {"DOI": "10.2/z"}, "title": "P"}]

    found = lookup_meta([3], tmp_path, s2_fetch=s2, crossref_fetch=lambda *_: {"update-to": []}, openalex_fetch=lambda *_: {})
    assert found[3]["retracted"] is False
    assert found[3]["retraction"] == NO_RETRACTION
    assert lookup_meta([9], tmp_path / "empty", s2_fetch=lambda *_: (_ for _ in ()).throw(TimeoutError())) is None
    body = label_payload([{"corpusid": 9, "title": "Solo"}], [], None, {})
    assert body["ok"] is False and body["note"] == OFFLINE_NOTE


def test_cosine_uses_stored_vectors_not_a_new_search():
    def encode(_texts):
        return [[1.0, 0.0]]

    def vector_of(cid):
        return [1.0, 0.0] if cid == 1 else [0.0, 1.0]

    scores = cosines_for([1, 2], encode, vector_of, "pregunta")
    assert scores[1] > 0.99
    assert abs(scores[2]) < 1e-9


def test_source_pdf_stays_out_of_the_figure_sandbox(tmp_path):
    folder = tmp_path / "1"
    (folder / "figures").mkdir(parents=True)
    (folder / "source.pdf").write_bytes(b"%PDF")
    assert resolve_figure(tmp_path, "1", "source.pdf") is None
    assert resolve_source_pdf(tmp_path, "1", "source.pdf") == (folder / "source.pdf").resolve()
    assert resolve_source_pdf(tmp_path, "1", "../source.pdf") is None
    assert resolve_source_pdf(tmp_path, "../1", "source.pdf") is None
