"""Top-k de frases por coseno. No exige las mismas palabras ni el mismo idioma.

El encoder de la consulta ya está en el repo: SPECTER2 (`rrm.search.encode`).
Si ese paquete no está, se usa una bolsa local con el glosario de panorama.
"""

import hashlib
import os
import threading
import time
import unicodedata
from pathlib import Path

import numpy as np

from rrm.reader.phrases import _chunk_in, query_tokens, rank_phrases
from rrm.search.labels import cosine

_DIM = 48
_CAP = 12
_PER_PAPER = 3
_encoder = None


def _fold(text):
    raw = unicodedata.normalize("NFD", text or "").casefold()
    return "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")


def _gloss():
    from rrm.panorama import _GLOSS

    return _GLOSS


def local_encode(texts):
    gloss = _gloss()
    out = np.zeros((len(list(texts)), _DIM), dtype=np.float32)
    for index, text in enumerate(texts):
        for word in query_tokens(_fold(text))[0]:
            token = gloss.get(word, word)
            digest = hashlib.sha256(token.encode()).digest()
            bucket = int.from_bytes(digest[:2], "little") % _DIM
            sign = 1.0 if digest[2] & 1 else -1.0
            out[index, bucket] += sign
    return out


_encoder_lock = threading.Lock()


def load_specter():
    """El QueryEncoder de main. Lo comparten las frases y los pasajes."""
    global _encoder
    with _encoder_lock:
        if _encoder is None:
            from rrm.search.encode import QueryEncoder

            _encoder = QueryEncoder()
        return _encoder


def specter_encode(texts):
    """Un solo hilo carga el modelo. Dos imports a la vez rompen el primero."""
    return np.asarray(load_specter().encode(list(texts)), dtype=np.float32)


def encode_texts(texts):
    """SPECTER2 si carga. Si no, la bolsa local. `RRM_PHRASE_ENCODER=local` lo fuerza."""
    choice = os.environ.get("RRM_PHRASE_ENCODER", "auto").strip().lower()
    if choice == "local":
        return local_encode(texts)
    try:
        return specter_encode(texts)
    except Exception:
        return local_encode(texts)


def _phrase_text(row):
    latex = " ".join(row.get("latex") or [])
    return ((row.get("text") or "") + " " + latex).strip()


def text_rows(rows):
    return [row for row in rows or [] if isinstance(row, dict) and str(row.get("text") or "").strip()]


def commit_phrases(folder, reload, commit, encode=None):
    """Escribe frases y vectores y hace commit antes de soltar el volumen.

    Un reload de Modal tira lo que todavía no se commiteó. Por eso el commit
    va en la misma sección que la escritura, no en un hilo que termina después.
    """
    from rrm.reader.phrases import read_phrases, write_phrases
    from rrm.reader.pipeline import load_paper

    started = time.perf_counter()
    folder = Path(folder)
    try:
        reload()
    except Exception:
        pass
    had_phrases = (folder / "phrases.json").is_file()
    had_vectors = (folder / "phrases.npy").is_file()
    rows = text_rows(read_phrases(folder))
    vecs = read_vectors(folder, len(rows)) if rows else None
    error = ""
    if not rows or vecs is None:
        try:
            if not rows:
                paper = load_paper(folder)
                if isinstance(paper, dict) and paper.get("blocks"):
                    rows = text_rows(write_phrases(folder, paper))
            if rows and read_vectors(folder, len(rows)) is None:
                saved = save_vectors(folder, rows, encode=encode)
                if saved is None:
                    error = "encode"
        except Exception as err:
            error = f"{type(err).__name__}: {err}"[:180]
        if (folder / "phrases.json").is_file() or (folder / "phrases.npy").is_file():
            try:
                commit()
            except Exception as err:
                error = error or type(err).__name__
        rows = text_rows(read_phrases(folder))
        vecs = read_vectors(folder, len(rows)) if rows else None
    if rows and vecs is not None:
        try:
            if append_abstract(folder, rows, encode=encode):
                try:
                    commit()
                except Exception as err:
                    error = error or type(err).__name__
                rows = text_rows(read_phrases(folder))
                vecs = read_vectors(folder, len(rows)) if rows else None
        except Exception as err:
            error = error or f"{type(err).__name__}: {err}"[:180]
    return {
        "ready": bool(rows) and vecs is not None,
        "rows": len(rows or []),
        "had_phrases": had_phrases,
        "had_vectors": had_vectors,
        "seconds": round(time.perf_counter() - started, 3),
        "error": error,
    }


def save_vectors(folder, rows, encode=None):
    """SPECTER2 de las frases, al lado de phrases.json."""
    usable = text_rows(rows)
    if not usable:
        return None
    encode = encode or specter_encode
    vecs = np.asarray(encode([_phrase_text(row) for row in usable]), dtype=np.float32)
    if vecs.ndim != 2 or vecs.shape[0] != len(usable):
        return None
    path = Path(folder) / "phrases.npy"
    tmp = path.with_name(f".phrases.{os.getpid()}.npy")
    np.save(tmp, vecs)
    os.replace(tmp, path)
    return vecs


def read_vectors(folder, n):
    path = Path(folder) / "phrases.npy"
    if n <= 0 or not path.is_file():
        return None
    try:
        vecs = np.load(path, allow_pickle=False)
    except Exception:
        return None
    if getattr(vecs, "ndim", 0) != 2 or vecs.shape[0] != int(n):
        return None
    return np.asarray(vecs, dtype=np.float32)


def phrase_ids(ids, focus):
    """Con paper abierto, el coseno usa solo su carpeta.

    La UI manda los 10 de la ráfaga en `ids` y el abierto en `focus`. Mezclarlos
    fue el fallo: el margen 0.05 se llenaba de Longformer, Big Bird y Linformer.
    `RRM_PHRASE_NEIGHBORS=1` vuelve a rankear toda la ráfaga.
    """
    if os.environ.get("RRM_PHRASE_NEIGHBORS") == "1":
        return list(ids or [])
    if focus not in (None, ""):
        return [focus]
    return list(ids or [])


def load_aligned(root, ids):
    """Frases con vector guardado. `missing` si hay texto y todavía no hay .npy."""
    from rrm.reader.phrases import read_phrases

    base = Path(root) if root else None
    if base is None:
        return [], None, False
    rows, mats, missing = [], [], False
    for raw in ids or []:
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        got = text_rows(read_phrases(base / str(cid)))
        if not got:
            continue
        for row in got:
            if row.get("paper") in (None, ""):
                row["paper"] = cid
        vecs = read_vectors(base / str(cid), len(got))
        if vecs is None:
            missing = True
            continue
        rows.extend(got)
        mats.append(vecs)
    if not rows:
        return [], None, missing
    return rows, np.vstack(mats), missing


def append_abstract(folder, rows, encode=None):
    """Encodea solo las frases del abstract que el almacén viejo no tenía."""
    if os.environ.get("RRM_PHRASE_ABSTRACT", "1") == "0":
        return False
    from rrm.reader.phrases import append_phrase_rows, collect_phrases
    from rrm.reader.pipeline import load_paper

    paper = load_paper(folder)
    if not isinstance(paper, dict) or not paper.get("blocks"):
        return False
    have = {(row.get("text") or "").strip() for row in rows}
    extra = [
        row for row in text_rows(collect_phrases(paper))
        if (row.get("text") or "").strip() not in have
    ]
    if not extra:
        return False
    old = read_vectors(folder, len(rows))
    if old is None:
        return False
    encode = encode or specter_encode
    new = np.asarray(encode([_phrase_text(row) for row in extra]), dtype=np.float32)
    if new.ndim != 2 or new.shape[0] != len(extra) or tuple(new.shape[1:]) != tuple(old.shape[1:]):
        return False
    append_phrase_rows(folder, extra)
    path = Path(folder) / "phrases.npy"
    tmp = path.with_name(f".phrases.{os.getpid()}.npy")
    np.save(tmp, np.vstack([old, new]))
    os.replace(tmp, path)
    return True


def _norm(text):
    import re
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def _literal(query, row):
    left, right = _norm(query), _norm(row.get("text"))
    if len(left) < 24 or len(right) < 24:
        return False
    return left in right or right in left


def _score_rows(usable, query, mat, chunks, raw=""):
    scored = []
    for row, vec in zip(usable, mat):
        score = cosine(query, vec)
        if score is None:
            continue
        if _literal(raw, row):
            bonus = 2
        elif chunks and any(_chunk_in(chunk, row) for chunk in chunks):
            bonus = 1
        else:
            bonus = 0
        scored.append((bonus, score, row))
    return scored


def rank_similar(rows, text, encode=None, vectors=None):
    """Las frases más cercanas a la explicación. Tope 3 por paper y 12.

    Con `vectors` solo se encodea la explicación. El producto es el coseno,
    el mismo margen 0.05 de antes.
    """
    words, chunks = query_tokens(text or "")
    usable = text_rows(rows)
    if not (text or "").strip() or not usable:
        return [], 0
    if chunks and not words:
        return rank_phrases(usable, text)
    encode = encode or local_encode
    if vectors is not None:
        mat = np.asarray(vectors, dtype=np.float32)
        if mat.ndim != 2 or mat.shape[0] != len(usable):
            return [], 0
        query = np.asarray(encode([text]), dtype=np.float32).reshape(-1)
        if query.shape != mat.shape[1:]:
            raise ValueError(f"vector {tuple(query.shape)} != {tuple(mat.shape)}")
        scored = _score_rows(usable, query, mat, chunks, text)
    else:
        try:
            vecs = np.asarray(encode([text] + [_phrase_text(row) for row in usable]), dtype=np.float32)
        except Exception:
            return [], 0
        if vecs.ndim != 2 or vecs.shape[0] != len(usable) + 1:
            return [], 0
        scored = _score_rows(usable, vecs[0], vecs[1:], chunks, text)
    if scored:
        best = max(item[1] for item in scored)
        # Una frase lejos de la mejor no entra: si no, «te faltó» cita cualquier cosa.
        scored = [item for item in scored if item[0] or item[1] >= best - 0.05]
    scored.sort(key=lambda item: (-item[0], -item[1]))
    picked, per = [], {}
    for _bonus, _score, row in scored:
        pid = row.get("paper")
        if per.get(pid, 0) >= _PER_PAPER:
            continue
        per[pid] = per.get(pid, 0) + 1
        picked.append(row)
        if len(picked) >= _CAP:
            break
    return picked, len(scored)
