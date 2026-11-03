#!/usr/bin/env python3
"""Máscara de portada para un rows.parquet que ya existe. No re-embebe ni borra.

Escribe ``junk_mask.npy``: un bool por fila, en el mismo orden que el parquet.
La búsqueda lo usa si está junto al parquet y el largo coincide.

    python3 scripts/passage_junk_mask.py --rows rows.parquet --out junk_mask.npy

``--sample N`` clasifica N filas al azar e imprime el conteo. No escribe máscara:
una máscara a medias no se puede subir al volumen.

En la caja, con el parquet ya en disco (no hace falta Modal para clasificar):

    python3 scripts/passage_junk_mask.py --rows /passages/rows.parquet --out junk_mask.npy
    modal volume put rrm-data junk_mask.npy /passages/junk_mask.npy --force

Eso solo agrega el archivo. No toca ``rows.parquet`` ni ``faiss.index``.
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rrm.reader.passage_junk import is_junk_passage  # noqa: E402


def _columns(schema_names):
    want = [name for name in ("text", "latex", "kind", "id") if name in schema_names]
    if "text" not in want and "latex" not in want:
        raise SystemExit("el parquet no tiene columna text ni latex")
    return want


def _column(table, name, n):
    if name not in table.column_names:
        return [""] * n
    return table.column(name).to_pylist()


def _scan(table):
    n = table.num_rows
    texts = _column(table, "text", n)
    latexs = _column(table, "latex", n)
    kinds = _column(table, "kind", n)
    ids = _column(table, "id", n)
    mask = []
    examples = []
    for text, latex, kind, row_id in zip(texts, latexs, kinds, ids):
        junk = bool(is_junk_passage(text, latex, kind))
        mask.append(junk)
        if junk and len(examples) < 8:
            preview = " ".join(str(text or latex or "").split())[:180]
            examples.append((str(row_id or ""), preview))
    return mask, examples


def _report(n, junk, examples, sampled_from):
    pct = (100.0 * junk / n) if n else 0.0
    scope = f"muestra {n} de {sampled_from}" if sampled_from else f"filas {n}"
    print(f"junk {junk} / {scope} ({pct:.2f}%)")
    for row_id, preview in examples:
        print(f"  - {row_id}: {preview}")


def main():
    parser = argparse.ArgumentParser(description="Máscara booleana de filas de portada")
    parser.add_argument("--rows", required=True, help="rows.parquet")
    parser.add_argument("--out", help="ruta de junk_mask.npy")
    parser.add_argument("--sample", type=int, default=0, help="solo N filas, sin escribir")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.sample and args.out:
        raise SystemExit("--sample no escribe máscara; quita --out")
    path = Path(args.rows)
    if not path.is_file():
        raise SystemExit(f"no está el parquet: {path}")

    import numpy as np
    import pyarrow.parquet as pq

    columns = _columns(set(pq.read_schema(path).names))
    if args.sample:
        total = int(pq.ParquetFile(path).metadata.num_rows)
        if total <= 0:
            raise SystemExit("el parquet no tiene filas")
        n = min(int(args.sample), total)
        picks = set(int(i) for i in np.random.default_rng(int(args.seed)).choice(total, size=n, replace=False))
        seen = 0
        junk = 0
        examples = []
        for batch in pq.ParquetFile(path).iter_batches(columns=columns, batch_size=4096):
            mask, _examples = _scan(batch)
            texts = _column(batch, "text", batch.num_rows)
            latexs = _column(batch, "latex", batch.num_rows)
            ids = _column(batch, "id", batch.num_rows)
            for bit, text, latex, row_id in zip(mask, texts, latexs, ids):
                if seen in picks:
                    junk += int(bit)
                    if bit and len(examples) < 8:
                        preview = " ".join(str(text or latex or "").split())[:180]
                        examples.append((str(row_id or ""), preview))
                seen += 1
        _report(n, junk, examples, sampled_from=total)
        return

    mask, examples = _scan(pq.read_table(path, columns=columns))
    _report(len(mask), sum(1 for bit in mask if bit), examples, sampled_from=None)
    if not args.out:
        return
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, np.asarray(mask, dtype=bool))
    print(f"escribí {out} ({len(mask)} bool)")


if __name__ == "__main__":
    main()
