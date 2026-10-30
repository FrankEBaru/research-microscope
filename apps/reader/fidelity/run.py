#!/usr/bin/env python3
"""Banco de fidelidad (RRM-8 B): LaTeX real (pdflatex) como árbitro del pipeline pandoc -> KaTeX.
Uso: python3 run.py [--n-random 30]   Salida: out/report.json, out/report.md, out/contact.html"""
import argparse, html, json, re, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from cases import PREAMBLE, cases  # noqa
from build_data import flatten_and_number  # noqa

OUT = Path(__file__).parent / "out"; DOCS = OUT / "docs"; REF = OUT / "ref"; OURS = OUT / "ours"
for d in (DOCS, REF, OURS): d.mkdir(parents=True, exist_ok=True)

def doc(kind, tex):
    body = rf"\[ {tex} \]" if kind == "display" else tex
    return "\\documentclass[varwidth=16cm,border=8pt]{standalone}\n" + PREAMBLE + "\\begin{document}\n" + body + "\n\\end{document}\n"

def reference(cid, kind, tex):
    """Compila con LaTeX real y rasteriza. Devuelve (ok, texto_pdf, log)."""
    f = DOCS / f"{cid}.tex"; f.write_text(doc(kind, tex))
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{cid}.tex"], cwd=DOCS, capture_output=True, text=True, timeout=60)
    pdf = DOCS / f"{cid}.pdf"
    if r.returncode != 0 or not pdf.exists():
        return False, "", re.findall(r"^! .*", r.stdout, re.M)[:1]
    subprocess.run(["pdftocairo", "-png", "-singlefile", "-r", "170", str(pdf), str(REF / cid)], check=True)
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    return True, txt, []

def first_math(node):
    if isinstance(node, dict):
        if node.get("t") == "Math": return node["c"]
        for v in node.values():
            m = first_math(v)
            if m: return m
    elif isinstance(node, list):
        for v in node:
            m = first_math(v)
            if m: return m
    return None

def via_pandoc(cid):
    """El MISMO documento pasa por pandoc, como en build_data.py; devuelve el LaTeX que recibiría KaTeX."""
    flat = flatten_and_number(DOCS, f"{cid}.tex", out=f"{cid}.flat.tex")  # mismo paso que build_data.py
    r = subprocess.run(["pandoc", flat, "-f", "latex", "-t", "json"], cwd=DOCS, capture_output=True, text=True)
    if r.returncode != 0: return None, "pandoc: " + r.stderr[:100]
    m = first_math(json.loads(r.stdout)["blocks"])
    return (m[1], "") if m else (None, "pandoc no produjo ninguna fórmula")

def crop(img, pad=6):
    a = np.array(img.convert("L")); ys, xs = np.where(a < 235)
    if len(ys) == 0: return img.convert("L")
    return img.convert("L").crop((max(xs.min() - pad, 0), max(ys.min() - pad, 0), xs.max() + pad, ys.max() + pad))

def ssim(a, b, k=7):
    a = a.astype(float); b = b.astype(float)
    def mean(x):
        c = np.cumsum(np.cumsum(np.pad(x, ((1, 0), (1, 0))), 0), 1)
        return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)
    ma, mb = mean(a), mean(b); va = mean(a * a) - ma ** 2; vb = mean(b * b) - mb ** 2; cov = mean(a * b) - ma * mb
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    return float(np.mean(((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma ** 2 + mb ** 2 + c1) * (va + vb + c2))))

def compare(cid):
    r, o = crop(Image.open(REF / f"{cid}.png")), crop(Image.open(OURS / f"{cid}.png"))
    asp = (o.width / o.height) / (r.width / r.height)
    o2 = o.resize(r.size, Image.LANCZOS)
    blur = lambda im: np.array(im.filter(ImageFilter.GaussianBlur(1.6)))
    return ssim(blur(r), blur(o2)), asp

alnum = lambda s: sorted(re.findall(r"[A-Za-z0-9]", s))
def content_diff(ref_txt, our_txt):
    from collections import Counter
    a, b = Counter(alnum(ref_txt)), Counter(alnum(our_txt))
    miss = sum((a - b).values()); extra = sum((b - a).values()); tot = max(sum(a.values()), 1)
    return miss, extra, tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n-random", type=int, default=30); n = ap.parse_args().n_random
    cs = cases(n)
    res = []; todo = []
    for cid, fam, kind, tex in cs:
        ok, ref_txt, err = reference(cid, kind, tex)
        row = {"id": cid, "family": fam, "tex": tex, "latex_ok": ok, "latex_err": err}
        if ok:
            ktex, perr = via_pandoc(cid); row["pandoc_tex"] = ktex; row["pandoc_err"] = perr
            if ktex: todo.append({"id": cid, "tex": ktex, "display": True})
        row["_ref_txt"] = ref_txt; res.append(row)
    (OUT / "todo.json").write_text(json.dumps(todo))
    subprocess.run(["node", str(Path(__file__).parent / "render.mjs"), str(OUT / "todo.json"), str(OURS), str(OUT / "rendered.json")], check=True)
    rendered = {r["id"]: r for r in json.loads((OUT / "rendered.json").read_text())}
    for row in res:
        rr = rendered.get(row["id"])
        if not row["latex_ok"]: row["status"] = "INVALIDO_LATEX"; continue
        if not rr: row["status"] = "FALLA_PANDOC"; continue
        row["katex_err"] = rr["error"]
        if rr["error"]: row["status"] = "FALLA_KATEX"; continue
        row["ssim"], row["aspect"] = compare(row["id"])
        row["miss"], row["extra"], row["tot"] = content_diff(row["_ref_txt"], rr["text"])
        bad = row["ssim"] < 0.45 or not (0.8 < row["aspect"] < 1.25) or (row["tot"] >= 8 and row["miss"] > 0.15 * row["tot"])
        row["status"] = "REVISAR" if bad else "PASA"
    for r in res: r.pop("_ref_txt", None)
    (OUT / "report.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    # resumen por familia
    fams = {}
    for r in res: fams.setdefault(r["family"], []).append(r["status"])
    lines = ["| familia | n | PASA | REVISAR | FALLA_KATEX | FALLA_PANDOC | INVALIDO_LATEX |", "|---|---|---|---|---|---|---|"]
    for f, st in sorted(fams.items()):
        lines.append(f"| {f} | {len(st)} | " + " | ".join(str(st.count(k)) for k in ["PASA", "REVISAR", "FALLA_KATEX", "FALLA_PANDOC", "INVALIDO_LATEX"]) + " |")
    allst = [r["status"] for r in res]
    lines.append(f"| **total** | {len(allst)} | " + " | ".join(str(allst.count(k)) for k in ["PASA", "REVISAR", "FALLA_KATEX", "FALLA_PANDOC", "INVALIDO_LATEX"]) + " |")
    fails = [f"- `{r['id']}` ({r['status']}): {r.get('katex_err') or r.get('pandoc_err') or r.get('latex_err')}" for r in res if r["status"] not in ("PASA", "REVISAR")]
    (OUT / "report.md").write_text("\n".join(lines) + "\n\n" + "\n".join(fails) + "\n")
    # hoja de contacto
    rows = []
    for r in sorted(res, key=lambda r: (r["status"] == "PASA", r.get("ssim", -1))):
        img = lambda d: f'<img src="{d}/{r["id"]}.png">' if (OUT / d / f"{r['id']}.png").exists() else "—"
        rows.append(f'<tr class="{r["status"]}"><td>{r["id"]}<br><small>{r["family"]}</small></td><td>{img("ref")}</td><td>{img("ours")}</td><td>{r["status"]}<br>ssim {r.get("ssim", float("nan")):.2f} · asp {r.get("aspect", float("nan")):.2f}<br><small>{html.escape(str(r.get("katex_err") or r.get("pandoc_err") or r.get("latex_err") or ""))}</small></td></tr>')
    (OUT / "contact.html").write_text("<meta charset=utf-8><style>body{font:13px sans-serif}td{border-bottom:1px solid #ddd;padding:6px;vertical-align:middle}img{max-width:420px;max-height:150px}.FALLA_KATEX{background:#fdd}.REVISAR{background:#ffe9b5}.PASA{background:#eefbee}</style><table><tr><th>caso</th><th>LaTeX real (PDF)</th><th>pipeline (pandoc→KaTeX)</th><th>resultado</th></tr>" + "".join(rows) + "</table>")
    print("\n".join(lines))

if __name__ == "__main__": main()
