"""Consulta en inglés para SPECTER2. La búsqueda no llama a Meta.

SPECTER2 se entrenó en inglés. Una pregunta en español se traduce en CPU
con Helsinki-NLP/opus-mt-es-en antes del encode. Si el paper más cercano
queda por debajo de TOPIC_COSINE, la ráfaga lo dice.
"""

import re

TOPIC_COSINE = 0.60
TOPIC_NOTE = "Estos papers podrían no ser de tu tema; prueba en inglés o con otras palabras."
PREPARING = "Preparando los vectores de las frases…"

_MARK = re.compile(r"[¿¡áéíóúñü]", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_STOP = {
    "el", "la", "los", "las", "un", "una", "de", "del", "al", "que", "qué",
    "como", "cómo", "por", "para", "en", "con", "se", "su", "es", "son",
    "este", "esta", "porqué", "porque", "funciona", "atención", "atencion",
    "raíz", "raiz",
}
_MODEL = "Helsinki-NLP/opus-mt-es-en"
_tok = None
_mt = None


def looks_spanish(text) -> bool:
    """Acentos o dos palabras de parada. Una pregunta en inglés no entra."""
    raw = text or ""
    if _MARK.search(raw):
        return True
    words = [word.casefold() for word in _WORD.findall(raw)]
    if len(words) < 2:
        return False
    hits = sum(1 for word in words if word in _STOP)
    return hits >= 2


def to_english(text: str) -> str:
    """Traduce una frase. El modelo queda en memoria del proceso."""
    global _tok, _mt
    if _mt is None:
        import torch
        from transformers import MarianMTModel, MarianTokenizer

        _tok = MarianTokenizer.from_pretrained(_MODEL)
        _mt = MarianMTModel.from_pretrained(_MODEL)
        _mt.eval()
        _mt._torch = torch
    batch = _tok([text], return_tensors="pt", truncation=True, max_length=256)
    with _mt._torch.no_grad():
        out = _mt.generate(**batch, max_new_tokens=256)
    return _tok.decode(out[0], skip_special_tokens=True)


def retrieval_query(text, translate=None):
    """Texto que se encodea, y la traducción si la pregunta era española.

    Si la traducción falla, se busca el texto original y se marca igual,
    para no recomputar la ráfaga en cada visita.
    """
    raw = str(text or "")
    if not looks_spanish(raw):
        return raw, ""
    fn = translate or to_english
    try:
        done = str(fn(raw) or "").strip()
    except Exception:
        done = ""
    if not done:
        return raw, raw
    return done, done


def cache_miss_spanish(query, payload) -> bool:
    """Una ráfaga guardada antes de traducir no sirve para una pregunta en español."""
    if not looks_spanish(query):
        return False
    return not str((payload or {}).get("query_en") or "").strip()


def topic_fields(qvec, ids, vector_of, cosine):
    """Coseno del paper más cercano. La nota solo sale si ese coseno es bajo."""
    if qvec is None or vector_of is None:
        return {}
    best = None
    for raw in list(ids or [])[:10]:
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        try:
            vec = vector_of(cid)
        except Exception:
            vec = None
        score = cosine(qvec, vec) if vec is not None else None
        if score is None:
            continue
        best = score if best is None else max(best, score)
    if best is None:
        return {}
    out = {"topic_cosine": round(float(best), 4)}
    if best < TOPIC_COSINE:
        out["topic_note"] = TOPIC_NOTE
    return out
