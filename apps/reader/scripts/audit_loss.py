#!/usr/bin/env python3
"""Auditoría de pérdida: compara las palabras del LaTeX (pandoc -t plain, referencia independiente de mi conversor)
con las palabras que llegan al bundle de la UI. Reporta lo que falta."""
import collections, json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from build_data import plain, block_plain, note_texts  # noqa

ROOT = Path(__file__).resolve().parent.parent
aid = sys.argv[1] if len(sys.argv) > 1 else "1706.03762"
src = ROOT / ".cache" / f"{aid}.src"
ref = subprocess.run(["pandoc", "ms.tex", "-f", "latex", "-t", "markdown", "--wrap=none"], cwd=src, capture_output=True, text=True).stdout
bundle = json.loads((ROOT / "public" / "papers" / f"{aid}.json").read_text())
parts = []
def cells(rows):
    return " ".join(plain(c) for r in rows for c in r)
for b in bundle["blocks"]:
    parts.append(block_plain(b))
    parts += note_texts(b)
    if b["kind"] == "table":
        parts.append(cells(b["head"]) + " " + cells(b["body"]))
    if b["kind"] == "fig":
        parts.append(plain(b["caption"]))
text = " ".join(parts + [bundle.get("license") or "", " ".join(bundle.get("authorNotes", []))])
def clean(s):
    s = re.sub(r"\$\$.*?\$\$", " ", s, flags=re.S)
    s = re.sub(r"\$[^$]*\$", " ", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)
    s = re.sub(r"@[\w:./-]+", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\{[#.][^}]*\}|\{[a-z-]+=[^}]*\}", " ", s)
    return s
tok = lambda s: collections.Counter(w.lower() for w in re.findall(r"[A-Za-z]{4,}", clean(s)))
r, u = tok(ref), tok(text)
missing = r - u
tot = sum(r.values()); miss = sum(missing.values())
print(f"{aid}: {tot} palabras (≥4 letras) en la referencia; {miss} faltan en la UI ({100*miss/tot:.2f}%)")
print("faltan:", dict(missing.most_common(25)))
