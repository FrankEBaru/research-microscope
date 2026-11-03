#!/usr/bin/env python3
"""Fixtures sintéticos para construir y verificar la UI sin datos grabados.

    python3 scripts/build_ui_fixtures.py --out DIR

Escribe un directorio que ``rrm.offline`` carga tal cual: una pregunta
(``prueba de interfaz``), 24 papers de prueba, un mapa kNN, etiquetas, estados,
dos papers, notas y una respuesta de la caja. Todo el texto es inventado.
No llama a la red.
"""

import argparse
import json
import math
from pathlib import Path

SLUG = "prueba"
QUESTION = "prueba de interfaz"
ASK_TEXT = "Frase de prueba: la atención reemplaza la recurrencia."
BASE = 9100000
FULL = BASE + 1
ABSTRACT_ONLY = BASE + 8
FAILED = BASE + 10
FAIL_REASON = "no arXiv e-print and no open-access PDF"
EQ_TEX = "\\mathrm{Attention}(Q,K,V)=\\mathrm{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V"

VENUES = ["Revista de Prueba", "Congreso de Prueba", "Taller de Prueba", "Archivo de Prueba"]
GROUPS = [
    ("test group A", 380, 300, False),
    ("test group B", 1040, 280, False),
    ("test group C", 420, 740, False),
    ("test group D", 1250, 780, True),
]


def _t(text):
    return {"t": "text", "v": text}


def _m(tex):
    return {"t": "math", "v": tex}


def _flat(sents):
    return [node for sent in sents for node in sent]


def _p(bid, sents, **extra):
    return {"id": bid, "kind": "p", "sents": sents, "inlines": _flat(sents), **extra}


def _h(bid, level, text):
    return {"id": bid, "kind": "h", "level": level, "inlines": [_t(text)]}


def _ids(n):
    return [BASE + i for i in range(1, n + 1)]


def _paper_row(i, cid):
    return {
        "corpusid": cid,
        "title": f"Paper de prueba {i}",
        "year": None if i == 10 else 2014 + (i * 7) % 11,
        "venue": VENUES[i % len(VENUES)],
        "citationcount": 900 - 37 * i + (i % 3) * 11,
        "score": round(0.95 - 0.02 * i, 3),
        "is_cs": True,
    }


def _edges(ids):
    out = []
    seen = set()
    for i in range(len(ids)):
        for step in (3, 7):
            j = (i + step) % len(ids)
            a, b = (ids[i], ids[j]) if i > j else (ids[j], ids[i])
            if a != b and (a, b) not in seen and len(out) < 40:
                seen.add((a, b))
                out.append({"citing": a, "cited": b})
    return out


def _layout(ids, edges):
    points = []
    members = {g: [] for g in range(len(GROUPS))}
    for i, cid in enumerate(ids):
        members[i % len(GROUPS)].append(cid)
    for g, (_name, cx, cy, _far) in enumerate(GROUPS):
        ring = members[g]
        for slot, cid in enumerate(ring):
            angle = 2 * math.pi * slot / max(1, len(ring))
            radius = 0 if slot == 0 else 95 + 12 * (slot % 2)
            idx = ids.index(cid)
            item = {
                "corpusid": cid,
                "x": round(cx + radius * math.cos(angle), 2),
                "y": round(cy + radius * math.sin(angle), 2),
                "cluster": g,
                "rank": idx,
            }
            if idx < 10:
                item["focus"] = True
            points.append(item)
    points.sort(key=lambda p: p["rank"])
    groups = []
    for g, (name, cx, cy, far) in enumerate(GROUPS):
        row = {"id": g, "n": len(members[g]), "kind": "knn", "name": name, "cx": cx, "cy": cy, "r": 170}
        if far:
            row["far"] = True
        groups.append(row)
    return {
        "method": "specter2-knn",
        "width": 1600,
        "height": 1000,
        "points": points,
        "links": [{"citing": e["citing"], "cited": e["cited"], "kind": "citation"} for e in edges],
        "similarity": [],
        "groups": groups,
        "grouping": "knn",
        "neighbors": {"k": 8, "preserved": 0.62, "trustworthiness": 0.9},
        "cosine_min": 0.72,
        "variance": [0.4, 0.2],
    }


def _labels(ids):
    by_id = {}
    for i, cid in enumerate(ids, 1):
        by_id[str(cid)] = {
            "abstract": f"Resumen de prueba {i}. Texto inventado para probar la interfaz; no describe ningún trabajo real.",
            "authors": [f"Autora Prueba {i}", f"Autor Muestra {i}"],
            "tldr": f"Resumen corto de prueba {i}.",
            "survey": i == 4,
            "retracted": i == 6,
            "retraction": "Retractado (dato de prueba)" if i == 6 else "No encontré retractación en Crossref",
        }
    return {"ok": True, "reason": "", "note": "", "by_id": by_id, "survey_paper": None}


def _status(ids):
    rows = []
    for i, cid in enumerate(ids[:10], 1):
        if i <= 7:
            rows.append({"id": cid, "status": "done", "source": "latex", "stage": "full", "reason": None, "text": True})
        elif i <= 9:
            rows.append({"id": cid, "status": "abstract_only", "source": "abstract", "stage": "abstract_only", "reason": None, "text": False})
        else:
            rows.append({"id": cid, "status": "failed", "source": None, "stage": "stub", "reason": FAIL_REASON, "text": False})
    return {"papers": rows}


def _full_blocks():
    cite = {"t": "cite", "keys": ["r1"]}
    note = {"t": "note", "blocks": [{"id": "n1", "kind": "p", "inlines": [_t("Nota al pie de prueba: texto inventado.")]}]}
    table = {
        "id": "b12",
        "kind": "table",
        "label": "tab:prueba",
        "caption": [_t("Resultados de prueba (cifras inventadas).")],
        "head": [[[_t("Método")], [_t("Exactitud")], [_t("Pasos")]]],
        "body": [
            [[_t(f"Método de prueba {k}")], [_t(f"{acc}")], [_t(f"{steps}")]]
            for k, acc, steps in [(1, "71.2", "120"), (2, "74.8", "150"), (3, "69.5", "90"), (4, "78.1", "210"), (5, "80.4", "260"), (6, "76.3", "180")]
        ],
    }
    return [
        _p("b0", [
            [_t("Resumen de prueba: este paper es inventado para probar la interfaz."), _m("d_k")],
            [_t("No contiene texto de ningún trabajo real.")],
        ], abs=True),
        _h("b1", 1, "Introducción de prueba"),
        _p("b2", [
            [_t("Frase de prueba sobre contexto"), cite, _t(": la lectura enlaza cada nota con su fuente.")],
            [_t("Otra frase de prueba sin símbolos."), note],
        ]),
        _h("b3", 1, "Método de prueba"),
        _p("b4", [
            [_t("Frase de prueba sobre atención: cada posición pondera a las demás con "), _m("Q"), _t(" y "), _m("d_k"), _t(".")],
            [_t("La atención reemplaza la recurrencia en esta frase de prueba sobre "), _m("Q"), _t(".")],
        ]),
        {"id": "b5", "kind": "eq", "tex": EQ_TEX, "number": 1, "labels": ["eq:att"]},
        _p("b6", [[_t("Aquí "), _m("d_k"), _t(" es la dimensión de las claves, según esta frase de prueba.")]]),
        _h("b7", 2, "Subsección de prueba"),
        _p("b8", [[_t("Supongamos, como frase de prueba, que "), _m("X\\in\\mathbb{R}^{n\\times d}"), _t(" es la entrada.")]]),
        _h("b9", 1, "Resultados de prueba"),
        _p("b10", [[_t("La tabla de prueba compara seis métodos inventados.")]]),
        {"id": "b11", "kind": "fig", "label": "fig:prueba", "images": [], "caption": [_t("Figura de prueba sin imagen.")]},
        table,
        _p("b13", [[_t("Cierre de prueba: nada de esto proviene de un paper real.")]]),
    ]


def _paper_full():
    row = _paper_row(1, FULL)
    doc = {
        "corpusid": FULL,
        "title": row["title"],
        "authors": ["Autora Prueba 1", "Autor Muestra 1"],
        "date": "2020-01-01",
        "abstract": "Resumen de prueba: este paper es inventado para probar la interfaz.",
        "arxivId": "",
        "full": True,
        "stage": "full",
        "source": "latex",
        "license": None,
        "refs": {"r1": "Autora Prueba. Referencia de prueba inventada. Revista de Prueba, 2019."},
        "blocks": _full_blocks(),
    }
    return {"status": "done", "meta": {"corpusid": FULL, "status": "done", "stage": "full", "source": "latex", "reason": None}, "paper": doc}


def _paper_abstract():
    row = _paper_row(8, ABSTRACT_ONLY)
    abstract = "Resumen de prueba: solo hay abstract para este paper inventado."
    doc = {
        "corpusid": ABSTRACT_ONLY,
        "title": row["title"],
        "authors": ["Autora Prueba 8"],
        "date": "2021-01-01",
        "abstract": abstract,
        "arxivId": "",
        "full": False,
        "stage": "abstract_only",
        "source": "abstract",
        "refs": {},
        "blocks": [_p("b0", [[_t(abstract)]], abs=True)],
    }
    return {"status": "abstract_only", "meta": {"corpusid": ABSTRACT_ONLY, "status": "abstract_only", "stage": "abstract_only", "source": "abstract", "reason": None}, "paper": doc}


def _notes():
    base = {"paper": str(FULL)}

    def card(block, sent, note, cite, generated=True, **extra):
        return {
            "block_id": block, "sent_index": sent, "note": note, "cite": cite,
            "passage_id": "" if not generated else "p-prueba", "generated": generated,
            "section": extra.pop("section", "Método de prueba"), "occupy": [block], **base, **extra,
        }

    return {
        "notes": [
            card("b5", 0, "Nota de prueba: la ecuación pondera los valores con las claves.", "cada posición pondera a las demás", section="Método de prueba"),
            card("b4", 0, "Nota de prueba: Q reúne las consultas de la frase.", "cada posición pondera a las demás con $Q$", section="Método de prueba"),
            card("b6", 0, "Nota de prueba: d_k es la dimensión de las claves.", "es la dimensión de las claves", section="Método de prueba"),
            card("b8", 0, "Supuesto de prueba: la entrada tiene n filas y d columnas.", "Supongamos, como frase de prueba", generated=False, kind="supuesto", section="Subsección de prueba"),
        ],
        "artifacts": [
            {"block_id": "b5", "type": "con_sin", "why_look": "Mira qué pasa con el peso al dividir entre la raíz de d_k.", "tex": EQ_TEX, "drop": ""},
            {"block_id": "b8", "type": "forma", "kind": "forma", "label": "n × d", "tex": "n\\times d", "body": True},
        ],
        "usage": {"model": "", "license": "", "cost_usd": 0.0},
    }


def _ask_answer(stage):
    def item(text, cite, part):
        return {"text": text, "cite": cite, "paper_id": str(FULL), "section": "Método de prueba", "verified": part != "te_falto"}

    quote = "Frase de prueba sobre atención: cada posición pondera a las demás con $Q$ y $d_k$."
    return {
        "extracts": [{"paper": FULL, "section": "Método de prueba", "text": quote}],
        "papers": 1,
        "line": "",
        "empty": False,
        "matched": 1,
        "parts": {
            "coincide": [item("Dices que la atención reemplaza la recurrencia; el paper de prueba lo dice igual.", quote, "coincide")],
            "contradice": [item("El paper de prueba no dice que la convolución desaparezca.", quote, "contradice")],
            "sin_respaldo": [item("Nada en las frases de prueba respalda una ganancia de velocidad.", quote, "sin_respaldo")],
            "te_falto": [item("Falta mencionar la escala por la raíz de d_k.", quote, "te_falto")],
        },
        "note": "" if stage == "revisar" else "Respuesta de prueba, sin modelo.",
        "store": {"ready": 10, "total": 10},
    }


def _write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def build(out) -> Path:
    root = Path(out)
    ids = _ids(24)
    rows = [_paper_row(i, cid) for i, cid in enumerate(ids, 1)]
    edges = _edges(ids)
    _write(root / "manifest.json", {
        "version": 2,
        "synthetic": True,
        "queries": [{
            "slug": SLUG, "q": QUESTION, "paper_ids": ids[:10], "saved_papers": [FULL, ABSTRACT_ONLY],
            "panorama_mode": "sim", "panorama_fallback": True,
        }],
    })
    _write(root / "burst" / f"{SLUG}.json", {
        "query": QUESTION, "mode": "short", "papers": rows[:10], "similar": rows[10:],
        "edges": edges, "layout": _layout(ids, edges), "subtopics": [],
    })
    _write(root / "labels" / f"{SLUG}.json", _labels(ids))
    _write(root / "status" / f"{SLUG}.json", _status(ids))
    _write(root / "papers" / f"{FULL}.json", _paper_full())
    _write(root / "papers" / f"{ABSTRACT_ONLY}.json", _paper_abstract())
    _write(root / "notes" / f"{FULL}.json", _notes())
    _write(root / "ask" / "index.json", [
        {"focus": str(FULL), "text": ASK_TEXT, "stage": "frases", "file": "frases.json"},
        {"focus": str(FULL), "text": ASK_TEXT, "stage": "revisar", "file": "revisar.json"},
    ])
    _write(root / "ask" / "frases.json", _ask_answer("frases"))
    _write(root / "ask" / "revisar.json", _ask_answer("revisar"))
    return root


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fixtures sintéticos de la UI. Texto inventado, sin red.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    root = build(args.out)
    print(f"fixtures sintéticos en {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
