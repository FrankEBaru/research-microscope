"""Revisión por afirmación de la explicación del lector. Tres candidatos.

E1 ventana: la sección entera + las oraciones del paper más cercanas a cada afirmación.
E2 hoja:    lo de E1 + la hoja de respuestas precalculada (puntos clave y pasajes);
            «te faltó» sale de los puntos clave que ninguna afirmación tocó.
E2m:        E2 y el modelo elige cuáles puntos clave faltaron (el código verifica). **Es el de la app.**
E3 (agente con herramientas) perdió y vive en evals/rrm100/agent_e3.py.

Los modelos devuelven ids; el código copia el texto y descarta ids inventados.
"""

import json
import re
import time

from rrm.reader.explain import llm
from rrm.reader.explain.retrieve import _encode, passage_text, rank_units, unit_vectors
from rrm.reader.explain.section import numbered, paper_units, ptr_of, section_title, section_units

VERDICTS = ("coincide", "diverge", "contradice", "sin_respaldo")
PARTS = VERDICTS + ("te_falto",)
MAX_SECTION = 70

_RULES = (
    "You check a reader's own explanation of one section of a research paper against what the paper says. "
    "The explanation comes as numbered sentences. Split it into claims: one per sentence, unless a sentence joins two different ideas; "
    "then split it and give each part its own claim with the same n. `text` is the reader's words for that claim, copied exactly. "
    "Verdicts: "
    "coincide: the paper says the same thing (a paraphrase counts). "
    "diverge: partly right: the idea is in the paper but a detail is wrong, a needed condition is dropped, or it is overstated. "
    "contradice: the paper says something incompatible: the opposite, a different number, a different mechanism, never vs always. "
    "sin_respaldo: none of the given paper sentences talk about it. "
    "Judge only against the given sentences, never against your own knowledge. If a given sentence rules the claim out, it is contradice, not sin_respaldo. "
    "`why`: at most 35 words of plain English for a student: say what the paper actually says and, if the claim is off, how. "
    "Do not start with 'The claim' or 'The reader'. Use the paper's own terms only. "
    "`paper`: the ids (only the id, like b22#0, never the sentence text) of 1 to 3 paper sentences behind the verdict; empty only for sin_respaldo. "
)
_OTHERS = "`others`: ids of passages from other papers that would help the reader with this claim (often none). "
_MISSED_FREE = (
    "`missed`: up to 2 important ideas of the section the reader did not mention at all: "
    "`paper` ids that state it and `why`: at most 25 words, plain English, saying what to add."
)
_MISSED_POINTS = "`points`: ids of the key points this claim talks about (k ids), empty if none. "


def _claim_schema(points=False, others=False):
    props = {
        "n": {"type": "integer"}, "text": {"type": "string"},
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "why": {"type": "string"}, "paper": {"type": "array", "items": {"type": "string"}},
    }
    if points:
        props["points"] = {"type": "array", "items": {"type": "string"}}
    if others:
        props["others"] = {"type": "array", "items": {"type": "string"}}
    claim = {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}
    missed = {
        "type": "object", "additionalProperties": False,
        "properties": {"paper": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}},
        "required": ["paper", "why"],
    }
    top = {"claims": {"type": "array", "items": claim}}
    if not points:
        top["missed"] = {"type": "array", "items": missed}
    return {"type": "object", "additionalProperties": False, "properties": top, "required": list(top)}


def sentences(text):
    """Corte por oración (el de feedback.py, que respeta LaTeX y puntos y coma)."""
    from rrm.reader.feedback import _sentences

    return _sentences(text)


def _said(sents):
    return "\n".join(f"{i}. {s}" for i, s in enumerate(sents, 1))


def clean_why(text, n=45):
    """Sin basura del modelo (cadenas largas sin espacio que no son LaTeX, una palabra repetida 4+ veces)
    y a lo más n palabras. Si la limpieza se lleva más de la mitad, no hay «why»: mejor nada que ruido."""
    words = str(text or "").split()
    kept = []
    for word in words:
        if len(word) >= 28 and "$" not in word and "\\" not in word:
            continue
        if len(kept) >= 3 and all(k.casefold() == word.casefold() for k in kept[-3:]):
            continue
        kept.append(word)
    if words and len(" ".join(kept)) < len(" ".join(words)) / 2:
        return ""
    return _clip(" ".join(kept), n)


def _clip(text, n):
    return " ".join(" ".join(str(text or "").split()).split(" ")[:n]).strip()


class Context:
    """Lo que cada candidato necesita del paper abierto, calculado una vez."""

    def __init__(self, paper, section_id, folder=None, encode=None, base=None):
        self.paper = paper
        self.section_id = str(section_id)
        self.title = section_title(paper, section_id)
        self.section = section_units(paper, section_id)[:MAX_SECTION]
        self.units = paper_units(paper)
        self.by_id = {u["id"]: u for u in self.units}
        for unit in self.section:
            self.by_id.setdefault(unit["id"], unit)
        self.encode = encode
        self.folder = folder
        self.base = base
        self._vecs = None

    @property
    def vecs(self):
        if self._vecs is None:
            self._vecs = unit_vectors(self.units, self.folder, self.encode)
        return self._vecs

    def near(self, texts, k=4):
        """Por texto: las k oraciones del paper más cercanas que no están ya en la sección."""
        if not texts:
            return []
        inside = {u["id"] for u in self.section}
        qv = _encode(texts, self.encode)
        hits = rank_units(qv, self.units, self.vecs, k=k + 8)
        out = []
        for row in hits:
            out.append([u for u, _s in row if u["id"] not in inside][:k])
        return out


def _evidence_paper(ctx, sents, k_out=3):
    """La sección completa y, aparte, las oraciones de otras secciones cercanas a cada afirmación."""
    extra, seen = [], set()
    for row in ctx.near(sents, k=k_out):
        for unit in row:
            if unit["id"] not in seen:
                seen.add(unit["id"])
                extra.append(unit)
    text = f"Section «{ctx.title}», all its sentences:\n{numbered(ctx.section)}"
    if extra:
        text += "\n\nOther sentences of the same paper:\n" + "\n".join(f"[{u['id']}] ({u['section']}) {u['text']}" for u in extra)
    return text


def _cite(ctx, ptrs, limit=3):
    out = []
    for ptr in ptrs or []:
        ptr = ptr_of(ptr)
        unit = ctx.by_id.get(ptr)
        if unit and all(c["ptr"] != ptr for c in out):
            out.append({"ptr": ptr, "text": unit["text"], "section": unit.get("section") or "", "paper_id": str(ctx.paper.get("corpusid"))})
        if len(out) >= limit:
            break
    return out


def _others(passages, ids):
    by = {p["id"]: p for p in passages or []}
    out = []
    for ref in ids or []:
        found = re.search(r"[po]\d+", str(ref or ""))
        hit = by.get(found.group(0)) if found else None
        if hit and hit not in out:
            out.append({k: hit[k] for k in ("id", "text", "title", "paper_id", "section", "why", "adds", "url") if k in hit})
    return out[:2]


def _own_words(text, sentence):
    """El texto de la afirmación debe salir de la oración del lector; si no, la oración entera."""
    flat = " ".join(str(text or "").split())
    if flat and flat.casefold().strip(" .") in sentence.casefold():
        return flat
    return sentence


def assemble(ctx, sents, data, passages=None, points=None):
    """JSON del modelo → partes con texto copiado por el código. Ids inventados se caen."""
    parts = {part: [] for part in PARTS}
    order = []
    covered = set()
    for item in (data or {}).get("claims") or []:
        if not isinstance(item, dict):
            continue
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        if n < 1 or n > len(sents):
            continue
        verdict = item.get("verdict")
        if verdict not in VERDICTS:
            continue
        cites = _cite(ctx, item.get("paper"))
        if verdict != "sin_respaldo" and not cites:
            # Sin frase del autor no hay coincide/contradice que mostrar.
            verdict = "sin_respaldo"
        out = {
            "n": n, "text": _own_words(item.get("text"), sents[n - 1]), "why": clean_why(item.get("why")),
            "cites": cites if verdict != "sin_respaldo" else [],
            "others": _others(passages, item.get("others")),
            "verified": True,
        }
        if out["cites"]:
            out["cite"] = out["cites"][0]["text"]
            out["paper_id"] = out["cites"][0]["paper_id"]
            out["section"] = out["cites"][0]["section"]
            out["ptr"] = out["cites"][0]["ptr"]
        if verdict != "sin_respaldo":  # tocado, aunque sea mal: eso ya lo dice el veredicto
            for k in item.get("points") or []:
                found = re.search(r"k\d+", str(k))
                if found:
                    covered.add(found.group(0))
        parts[verdict].append(out)
        order.append((n, verdict))
    # Una oración que el modelo olvidó no desaparece: queda sin respaldo con aviso.
    seen_n = {n for n, _v in order}
    for n, sentence in enumerate(sents, 1):
        if n not in seen_n:
            parts["sin_respaldo"].append({"n": n, "text": sentence, "why": "", "cites": [], "others": [], "verified": False})
    if points is not None:
        # Cubierto también si una afirmación que coincide o diverge cita una frase del punto.
        cited = {c["ptr"] for v in ("coincide", "diverge", "contradice") for item in parts[v] for c in item.get("cites") or []}
        for point in points:
            if cited & set(point.get("ptrs") or []):
                covered.add(point["id"])
        picked = None
        if isinstance((data or {}).get("missed"), list):
            picked = []
            for item in data["missed"]:
                found = re.search(r"k\d+", str((item or {}).get("point") if isinstance(item, dict) else item))
                if found and found.group(0) not in picked:
                    picked.append(found.group(0))
        parts["te_falto"] = _missed_from_points(ctx, points, covered, passages, picked=picked)
    else:
        for item in ((data or {}).get("missed") or [])[:2]:
            if not isinstance(item, dict):
                continue
            cites = _cite(ctx, item.get("paper"), limit=2)
            if not cites:
                continue
            parts["te_falto"].append({"text": _clip(item.get("why"), 35), "why": _clip(item.get("why"), 35), "cites": cites,
                                      "cite": cites[0]["text"], "paper_id": cites[0]["paper_id"], "section": cites[0]["section"],
                                      "ptr": cites[0]["ptr"], "others": [], "verified": True})
    for part in VERDICTS:
        parts[part].sort(key=lambda x: x["n"])
    return parts


def _missed_from_points(ctx, points, covered, passages, limit=2, picked=None):
    """Puntos clave que nadie tocó. Con `picked` (ids que eligió el modelo) solo esos, en su orden."""
    out = []
    if picked is not None:
        by = {p["id"]: p for p in points}
        points = [by[k] for k in picked if k in by]
    for point in points:
        if point["id"] in covered or (picked is None and not point.get("core")):
            continue
        cites = _cite(ctx, point.get("ptrs"), limit=2)
        if not cites:
            continue
        helps = [p for p in passages or [] if p.get("point") == point["id"]]
        out.append({
            "text": point["point"], "why": point.get("why") or "", "point": point["id"], "cites": cites,
            "cite": cites[0]["text"], "paper_id": cites[0]["paper_id"], "section": cites[0]["section"], "ptr": cites[0]["ptr"],
            "others": _others(helps, [p["id"] for p in helps]), "verified": True,
        })
        if len(out) >= limit:
            break
    return out


_TOKENS = 2200  # p99 de una revisión sana: 1864 tokens. Más arriba solo hay bucles.


def salvage(text):
    """Afirmaciones completas de un JSON cortado (el modelo a veces entra en bucle: «jjjj…»)."""
    raw = str(text or "")
    start = raw.find('"claims"')
    if start < 0:
        return None
    start = raw.find("[", start)
    if start < 0:
        return None
    dec, pos, out = json.JSONDecoder(), start + 1, []
    while True:
        while pos < len(raw) and raw[pos] in " \n\r\t,":
            pos += 1
        if pos >= len(raw) or raw[pos] != "{":
            break
        try:
            obj, pos = dec.raw_decode(raw, pos)
        except ValueError:
            break
        if isinstance(obj, dict):
            out.append(obj)
    return {"claims": out} if out else None


def _run(payload, salt):
    """Una llamada; si sale cortada o ilegible, rescata lo completo y, si falta algo, una segunda con esfuerzo low."""
    from rrm.reader.metacall import response_text

    response, cost, seconds, hit = llm.call(payload, salt=salt)
    data = llm.json_of(response)
    cut = bool(((response or {}).get("incomplete_details") or {}).get("reason"))
    if data is not None and not cut:
        return data, cost, seconds, hit
    partial = salvage(response_text(response))
    retry = dict(payload, reasoning={"effort": "low"})
    try:
        response2, cost2, seconds2, _hit2 = llm.call(retry, salt=salt + "|retry")
    except Exception:
        return partial, cost, seconds, hit
    cost, seconds = llm.add(cost, cost2), seconds + seconds2
    data2 = llm.json_of(response2)
    if data2 is not None and not ((response2 or {}).get("incomplete_details") or {}).get("reason"):
        return data2, cost, seconds, hit
    return partial or salvage(response_text(response2)), cost, seconds, hit


def review_e1(ctx, text, *, model=None, effort="minimal", salt=""):
    sents = sentences(text)
    if not sents:
        return {part: [] for part in PARTS}, llm.add(None, None), {}
    user = f"{_evidence_paper(ctx, sents)}\n\nReader's explanation:\n{_said(sents)}"
    payload = llm.body(_RULES + _MISSED_FREE, user, _claim_schema(), "review", model=model, effort=effort, tokens=_TOKENS)
    data, cost, seconds, hit = _run(payload, salt)
    return assemble(ctx, sents, data), cost, {"llm_s": seconds, "cached": hit, "parsed": data is not None}


_MISSED_PICK = (
    "`missed`: up to 2 key points (k ids) the reader did not address at all, the most important first; "
    "never a point that any claim talks about, even wrongly. Empty if the reader covered the essentials. "
)


def review_e2(ctx, text, sheet, *, model=None, effort="minimal", salt="", use_passages=True, pick=False):
    sents = sentences(text)
    if not sents:
        return {part: [] for part in PARTS}, llm.add(None, None), {}
    points = (sheet or {}).get("points") or []
    passages = (sheet or {}).get("passages") or [] if use_passages else []
    key = "\n".join(f"[{p['id']}] {p['point']} (sentences: {', '.join(p['ptrs'])})" for p in points)
    user = f"{_evidence_paper(ctx, sents)}\n\nKey points of the section:\n{key}"
    if passages:
        user += "\n\nPassages from other papers:\n" + "\n".join(f"[{p['id']}] (for {p['point']}; {p['title']}) {p['text']}" for p in passages)
    user += f"\n\nReader's explanation:\n{_said(sents)}"
    rules = _RULES + _MISSED_POINTS + (_OTHERS if passages else "") + (_MISSED_PICK if pick else "")
    schema = _claim_schema(points=True, others=bool(passages))
    if pick:
        pick_item = {"type": "object", "additionalProperties": False, "properties": {"point": {"type": "string"}}, "required": ["point"]}
        schema["properties"]["missed"] = {"type": "array", "items": pick_item}
        schema["required"] = list(schema["properties"])
    payload = llm.body(rules, user, schema, "review", model=model, effort=effort, tokens=_TOKENS)
    data, cost, seconds, hit = _run(payload, salt)
    return assemble(ctx, sents, data, passages=passages, points=points), cost, {"llm_s": seconds, "cached": hit, "parsed": data is not None}
