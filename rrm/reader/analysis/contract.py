"""Contrato de salida por ítem y V0 (verificador por código).

Ítem que devuelve un candidato (sólo punteros):
    {kind: note|equation|definition|artifact, anchor: "b25#2" | "b26",
     why, explain_idea, ai_text, paper_quotes: [ptr], passages: [pid],
     artifact?: {claim, passages, figure_idea, knob, consequence, question}}

`materialize` copia el texto literal: del brief para el paper, de la base
para los pasajes. Un puntero inválido se cae, la nota no (salvo el ancla).
"""

from __future__ import annotations

import json
import os
import re
import subprocess

KINDS = ("note", "equation", "definition", "artifact")

ITEM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "anchor": {"type": "string"},
        "why": {"type": "string"},
        "explain_idea": {"type": "string"},
        "ai_text": {"type": "string"},
        "paper_quotes": {"type": "array", "items": {"type": "string"}},
        "passages": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["kind", "anchor", "why", "explain_idea", "ai_text", "paper_quotes", "passages"],
}

ARTIFACT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "anchor": {"type": "string"}, "claim": {"type": "string"}, "figure_idea": {"type": "string"},
        "knob": {"type": "string"}, "consequence": {"type": "string"}, "question": {"type": "string"},
        "paper_quotes": {"type": "array", "items": {"type": "string"}},
        "passages": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["anchor", "claim", "figure_idea", "knob", "consequence", "question", "paper_quotes", "passages"],
}


def _words(text):
    return set(re.findall(r"[a-z]{3,}", (text or "").lower()))


def repeats(ai_text, anchor_text):
    """La nota sólo repite la frase ancla (Jaccard alto y casi sin palabras nuevas)."""
    a, b = _words(ai_text), _words(anchor_text)
    if not a:
        return True
    new = len(a - b) / max(1, len(a))
    return new < 0.25


_MATH = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]", re.S)


def math_spans(text):
    return [next(g for g in m.groups() if g is not None) for m in _MATH.finditer(text or "")]


def katex_ok(texs):
    """Lista de bool. Sin node/katex devuelve todo True (no bloquea)."""
    if not texs:
        return []
    node_path = os.environ.get("RRM_KATEX_NODE_PATH", "")
    if not node_path:
        return [True] * len(texs)
    js = (
        "const katex=require('katex');const items=JSON.parse(require('fs').readFileSync(0,'utf8'));"
        "process.stdout.write(JSON.stringify(items.map(t=>{try{katex.renderToString(t,{throwOnError:true});return true}catch(e){return false}})));"
    )
    try:
        out = subprocess.run(["node", "-e", js], input=json.dumps(texs), capture_output=True, text=True, timeout=30,
                             env={**os.environ, "NODE_PATH": node_path})
        return json.loads(out.stdout)
    except Exception:
        return [True] * len(texs)


def _near(a, b):
    """Mismo bloque y a ±1 oración, o mismo puntero."""
    if a == b:
        return True
    ma, mb = re.match(r"(b\d+)#(\d+)$", a or ""), re.match(r"(b\d+)#(\d+)$", b or "")
    return bool(ma and mb and ma.group(1) == mb.group(1) and abs(int(ma.group(2)) - int(mb.group(2))) <= 1)


_PTR = re.compile(r"b\d+(?:#\d+)?")


def norm_ptr(raw):
    """«[b28#1]», «b28 #1», «anchor: b26» → «b28#1» / «b26»."""
    text = re.sub(r"\s+", "", str(raw or ""))
    m = _PTR.search(text)
    return m.group(0) if m else text


def v0(items, ix, offered_pids=None, max_items=15):
    """Descarta sólo lo roto. Devuelve (ok, dropped) con motivo por ítem."""
    ok, dropped = [], []
    offered = set(offered_pids or [])
    tex_checks = []
    for item in items:
        if not isinstance(item, dict):
            dropped.append({"item": item, "reason": "no_dict"})
            continue
        anchor = norm_ptr(item.get("anchor"))
        if not ix.valid(anchor):
            # Tolerancia: "b25" para un párrafo → primera oración.
            if anchor in {s["block"] for s in ix.brief["sents"]}:
                anchor = f"{anchor}#0"
            else:
                dropped.append({"item": item, "reason": "anchor_invalid"})
                continue
        item = dict(item, anchor=anchor)
        kind = item.get("kind") if item.get("kind") in KINDS else "note"
        item["kind"] = kind
        text = " ".join(str(item.get("ai_text") or "").split())
        if kind != "artifact":
            if len(text) < 30:
                dropped.append({"item": item, "reason": "empty"})
                continue
            if repeats(text, ix.text(anchor)):
                dropped.append({"item": item, "reason": "repeats_anchor"})
                continue
        item["ai_text"] = text
        quotes = [norm_ptr(p) for p in (item.get("paper_quotes") or []) if ix.valid(norm_ptr(p))]
        item["bad_quotes"] = len(item.get("paper_quotes") or []) - len(quotes)
        item["paper_quotes"] = list(dict.fromkeys(quotes))[:3]
        pids = [str(p) for p in (item.get("passages") or [])]
        good = [p for p in pids if (not offered or p in offered)]
        item["bad_passages"] = len(pids) - len(good)
        item["passages"] = list(dict.fromkeys(good))[:3]
        if any(_near(anchor, o["anchor"]) and kind == o["kind"] for o in ok):
            dropped.append({"item": item, "reason": "duplicate"})
            continue
        ok.append(item)
        tex_checks.append(math_spans(text))
    flat = [t for spans in tex_checks for t in spans]
    res = katex_ok(flat)
    out, k = [], 0
    for item, spans in zip(ok, tex_checks):
        good = res[k:k + len(spans)]
        k += len(spans)
        if not all(good):
            dropped.append({"item": item, "reason": "katex"})
            continue
        out.append(item)
    return out[:max_items], dropped


def materialize(item, ix, passage_rows):
    """Copia los textos literales. passage_rows: {pid: fila de la base}."""
    from rrm.reader.rights import clip_text, license_class

    out = dict(item)
    out["paper_quotes_text"] = [{"ptr": p, "text": ix.text(p)} for p in item.get("paper_quotes") or []]
    shown = []
    for pid in item.get("passages") or []:
        row = passage_rows.get(pid)
        if not row:
            continue
        closed = license_class(row.get("license") or "") != "open"
        body = (row.get("text") or "") or (row.get("latex") or "")
        shown.append({"pid": pid, "title": row.get("title") or "", "corpusid": row.get("corpusid"),
                      "url": row.get("url") or "", "closed": closed, "text": clip_text(body, 300) if closed else body[:900]})
    out["passages_text"] = shown
    out["anchor_text"] = ix.text(item.get("anchor") or "")
    out["labels"] = {"ai": "AI-generated", "paper": "From this paper", "others": "From other papers"}
    return out
