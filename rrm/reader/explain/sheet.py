"""Hoja de respuestas de una sección: puntos clave con punteros y pasajes que explican más.

Se arma al abrir el paper, antes de que el lector escriba. Dos llamadas a Muse:
1. puntos clave de la sección (cada uno con ids de oración) y consultas por punto;
2. filtro de pasajes de otros papers: queda solo el que explica más allá del texto.
Todo se guarda en disco; la revisión solo la lee.
"""

import json
import os
import re
import time
from pathlib import Path

from rrm.reader.explain import llm
from rrm.reader.explain.retrieve import passage_text
from rrm.reader.explain.section import numbered, ptr_of, section_title, section_units

VERSION = "s4"
MAX_UNITS = 70

_POINTS = (
    "You prepare an answer key for one section of a research paper, so a reader's own explanation can be checked later. "
    "The section comes as numbered sentences, each with an id in brackets. "
    "List the key points a reader should be able to explain after this section: between 3 and 7, most important first. "
    "Each point is one plain-English sentence of at most 25 words, faithful to the paper, with no new facts. "
    "`why` says in at most 20 simple words why the point matters or what it means for the reader. "
    "`ptrs` are the ids of the sentences that state the point (1 to 4 ids, copied exactly). "
    "`core` is true for the ideas the section exists to teach, false for supporting details. "
    "`queries` are 3 short search queries (at most 12 words each) to find other papers that explain this point: "
    "one that asks to explain it, one that summarizes it, and one that asks why it holds."
)

_FILTER = (
    "You check passages from OTHER papers against the key points of a section of the paper being read. "
    "Keep a passage only if it helps a reader understand a key point beyond what the section already says: "
    "it gives intuition, a derivation, an example, a consequence, or a clear restatement from another angle. "
    "Drop passages that only repeat the point, that are about something else, that are boilerplate, or that would confuse. "
    "Also drop passages from a different setting (graphs, images, code data, another task) unless they explain this exact idea, "
    "and passages that need the rest of their own paper to make sense. When in doubt, drop it: zero passages is a fine answer. "
    "For each kept passage give its id, the id of the key point it helps, what it adds (one of intuition, derivation, example, consequence, restatement), "
    "and `why`: at most 20 simple words on how it helps. Keep at most 2 passages per key point and at most 8 in total. "
    "Copy ids exactly."
)


def _points_schema():
    point = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "point": {"type": "string"}, "why": {"type": "string"},
            "ptrs": {"type": "array", "items": {"type": "string"}},
            "core": {"type": "boolean"},
            "queries": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["point", "why", "ptrs", "core", "queries"],
    }
    return {"type": "object", "additionalProperties": False, "properties": {"points": {"type": "array", "items": point}}, "required": ["points"]}


def _filter_schema():
    keep = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "passage": {"type": "string"}, "point": {"type": "string"},
            "adds": {"type": "string", "enum": ["intuition", "derivation", "example", "consequence", "restatement"]},
            "why": {"type": "string"},
        },
        "required": ["passage", "point", "adds", "why"],
    }
    return {"type": "object", "additionalProperties": False, "properties": {"keep": {"type": "array", "items": keep}}, "required": ["keep"]}


def _clip_words(text, n):
    words = " ".join(str(text or "").split()).split(" ")
    return " ".join(words[:n]).strip()


def key_points(title, units, *, model=None, effort="low", salt=""):
    """→ (puntos, costo, segundos). Cada punto: id k1…, point, why, ptrs válidos, core, queries."""
    ids = {u["id"] for u in units}
    user = f"Section: {title}\n\nSentences:\n{numbered(units, MAX_UNITS)}"
    payload = llm.body(_POINTS, user, _points_schema(), "points", model=model, effort=effort, tokens=3000)
    response, cost, seconds, _hit = llm.call(payload, salt=salt)
    data = llm.json_of(response) or {}
    points = []
    for item in data.get("points") or []:
        if not isinstance(item, dict):
            continue
        ptrs = []
        for raw in item.get("ptrs") or []:
            ptr = ptr_of(raw)
            if ptr in ids and ptr not in ptrs:
                ptrs.append(ptr)
        ptrs = ptrs[:4]
        point = _clip_words(item.get("point"), 32)
        if not point or not ptrs:
            continue
        points.append({
            "id": f"k{len(points) + 1}", "point": point, "why": _clip_words(item.get("why"), 26),
            "ptrs": ptrs, "core": bool(item.get("core")),
            "queries": [q for q in (" ".join(str(q).split()) for q in item.get("queries") or []) if q][:3],
        })
        if len(points) >= 7:
            break
    return points, cost, seconds


def candidate_passages(points, title, base, encode, exclude, per_query=6, limit=24):
    """Consultas por punto (explain / summarize / why + el punto mismo) → pasajes únicos."""
    from rrm.reader.explain.retrieve import _encode

    queries, owner = [], []
    for point in points:
        for query in [point["point"]] + list(point.get("queries") or []):
            queries.append(query)
            owner.append(point["id"])
    if not queries:
        return []
    vecs = _encode(queries, encode)
    found = {}
    for vec, pid in zip(vecs, owner):
        for row, score in base.search(vec.reshape(1, -1), k=per_query, exclude=exclude):
            key = str(row.get("id"))
            if key not in found or score > found[key]["score"]:
                found[key] = {"row": row, "score": score, "point": pid}
    ranked = sorted(found.values(), key=lambda item: -item["score"])[:limit]
    return ranked


def filter_passages(points, cands, *, model=None, effort="low", salt=""):
    if not cands or not points:
        return [], llm.add(None, None), 0.0
    keyed = "\n".join(f"[{p['id']}] {p['point']}" for p in points)
    listed = "\n".join(
        f"[p{i + 1}] ({c['row'].get('title') or 'paper'}; {c['row'].get('section') or ''}) {passage_text(c['row'], 500)}"
        for i, c in enumerate(cands)
    )
    user = f"Key points:\n{keyed}\n\nPassages from other papers:\n{listed}"
    payload = llm.body(_FILTER, user, _filter_schema(), "keep", model=model, effort=effort, tokens=2000)
    response, cost, seconds, _hit = llm.call(payload, salt=salt)
    data = llm.json_of(response) or {}
    valid_points = {p["id"] for p in points}
    kept, seen, per = [], set(), {}
    for item in data.get("keep") or []:
        if not isinstance(item, dict):
            continue
        ref = re.search(r"p(\d+)", str(item.get("passage") or ""))
        found = re.search(r"k\d+", str(item.get("point") or ""))
        if not ref or not found:
            continue
        index = int(ref.group(1)) - 1
        point = found.group(0)
        if index < 0 or index >= len(cands) or point not in valid_points or index in seen:
            continue
        if per.get(point, 0) >= 2:
            continue
        seen.add(index)
        per[point] = per.get(point, 0) + 1
        row = cands[index]["row"]
        kept.append({
            "id": f"p{len(kept) + 1}", "point": point, "adds": item.get("adds") or "restatement",
            "why": _clip_words(item.get("why"), 24),
            "paper_id": str(row.get("corpusid")), "title": str(row.get("title") or ""),
            "section": str(row.get("section") or ""), "text": passage_text(row),
            "row_id": str(row.get("id")), "score": round(cands[index]["score"], 4),
            "license": str(row.get("license") or ""), "url": str(row.get("url") or ""),
        })
        if len(kept) >= 8:
            break
    return kept, cost, seconds


def build_sheet(paper, section_id, *, base=None, encode=None, model=None, effort="low", passages=True, salt=""):
    """Hoja completa de una sección. `base=None` o `passages=False`: sin pasajes."""
    started = time.perf_counter()
    units = section_units(paper, section_id)
    title = section_title(paper, section_id)
    if not units:
        return {"version": VERSION, "section": str(section_id), "title": title, "points": [], "passages": [], "cost": llm.add(None, None), "seconds": 0.0}
    points, cost, _s1 = key_points(title, units, model=model, effort=effort, salt=salt)
    kept = []
    if passages and base is not None and points:
        cands = candidate_passages(points, title, base, encode, exclude=paper.get("corpusid"))
        kept, cost2, _s2 = filter_passages(points, cands, model=model, effort=effort, salt=salt)
        cost = llm.add(cost, cost2)
    return {
        "version": VERSION, "paper": str(paper.get("corpusid")), "section": str(section_id), "title": title,
        "points": points, "passages": kept, "cost": cost, "seconds": round(time.perf_counter() - started, 3),
    }


def sheet_path(folder, section_id):
    return Path(folder) / "explain" / f"sheet-{section_id}-{VERSION}.json"


def load_sheet(folder, section_id):
    path = sheet_path(folder, section_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("version") == VERSION else None


def save_sheet(folder, sheet):
    path = sheet_path(folder, sheet["section"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path
