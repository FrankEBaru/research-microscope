#!/usr/bin/env python3
"""Descarga los papers de ejemplo desde arXiv y construye los bundles que lee la UI.

- Los datos descargados NO se commitean (repo público; ver AGENTS.md): salen en
  `public/papers/` y `.cache/`, ambos en .gitignore. Se regeneran con `npm run data`.
- En una máquina nueva, restaurar el Release `artifacts/RRM-11-reader-data-2026-10-29`
  (ver README) antes de volver a bajar arXiv. Si `.cache/` ya existe, no hay red.
- arXiv: 1 petición cada 3 s (ToS). Se cachea todo en `.cache/`.
- Cada ancla del contenido curado (`content/*.json`) se resuelve por CITA TEXTUAL:
  si la cita no aparece exactamente una vez en el paper, el build falla.
"""
import html
import json
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
OUT = ROOT / "public" / "papers"
CONTENT = ROOT / "content"
UA = "research-microscope-reader/0.1 (student prototype; contact via GitHub FrankEBaru)"
_last = [0.0]


def polite_get(url: str) -> bytes:
    wait = 3.2 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    _last[0] = time.time()
    return data


def cached(name: str, url: str) -> Path:
    CACHE.mkdir(exist_ok=True)
    p = CACHE / name
    if not p.exists():
        print(f"  descargando {url}")
        p.write_bytes(polite_get(url))
    return p


# ------------------------------------------------------------------ metadatos
def abs_meta(arxiv_id: str) -> dict:
    p = cached(f"{arxiv_id}.abs.html", f"https://arxiv.org/abs/{arxiv_id}")
    h = p.read_text(encoding="utf-8", errors="replace")

    def one(name):
        m = re.search(rf'<meta name="{name}" content="(.*?)"\s*/?>', h, re.S)
        return html.unescape(m.group(1)).strip() if m else None

    authors = [html.unescape(a).strip() for a in re.findall(r'<meta name="citation_author" content="(.*?)"', h)]
    # "Vaswani, Ashish" -> "Ashish Vaswani"
    authors = [" ".join(reversed([x.strip() for x in a.split(",", 1)])) if "," in a else a for a in authors]
    abstract = one("citation_abstract") or ""
    abstract = re.sub(r"\s+", " ", abstract.replace("\n", " ")).strip()
    return {
        "arxivId": arxiv_id,
        "title": one("citation_title"),
        "authors": authors,
        "date": one("citation_date"),
        "abstract": abstract,
    }


# ------------------------------------------------------------- AST de pandoc
def clean_math(tex: str) -> str:
    """Normaliza LaTeX que KaTeX no acepta, sin cambiar el significado: \\label (no renderiza) y \\hat \\mathbb{E} -> \\hat{\\mathbb{E}}."""
    tex = re.sub(r"\\label\{[^}]*\}", "", tex)
    return re.sub(r"\\(hat|tilde|bar|vec|dot|ddot|widehat|widetilde|overline)\s*(\\[A-Za-z]+\{[^{}]*\})", r"\\\1{\2}", tex)


def inl(nodes):
    out = []
    for x in nodes:
        t = x["t"]
        if t == "Str":
            out.append({"t": "text", "v": x["c"]})
        elif t in ("Space", "SoftBreak"):
            out.append({"t": "text", "v": " "})
        elif t == "LineBreak":
            out.append({"t": "text", "v": " "})
        elif t == "Math":
            kind, tex = x["c"]
            node = {"t": "math", "v": clean_math(tex), "display": kind["t"] == "DisplayMath"}
            lbl = re.findall(r"\\label\{([^}]*)\}", tex)
            if lbl:
                node["labels"] = lbl
            out.append(node)
        elif t == "Emph":
            out.append({"t": "em", "c": inl(x["c"])})
        elif t == "Strong":
            out.append({"t": "strong", "c": inl(x["c"])})
        elif t == "SmallCaps" or t == "Span":
            out.append({"t": "span", "c": inl(x["c"][-1] if t == "Span" else x["c"])})
        elif t == "Quoted":
            q = x["c"][0]["t"]
            o, c = ("“", "”") if q == "DoubleQuote" else ("‘", "’")
            out.append({"t": "text", "v": o})
            out += inl(x["c"][1])
            out.append({"t": "text", "v": c})
        elif t == "Cite":
            keys = [c["citationId"] for c in x["c"][0]]
            out.append({"t": "cite", "keys": keys})
        elif t == "Link":
            attr, content, target = x["c"]
            out.append({"t": "link", "href": target[0], "c": inl(content)})
        elif t == "Code":
            out.append({"t": "code", "v": x["c"][1]})
        elif t == "Note":
            out.append({"t": "note", "blocks": blocks(x["c"])})
        elif t == "Image":
            pass
        else:
            out.append({"t": "text", "v": ""})
    return out


def plain(inls) -> str:
    """Texto plano de una lista de inlines; la matemática va como $latex$."""
    s = []
    for x in inls:
        t = x["t"]
        if t == "text":
            s.append(x["v"])
        elif t == "math":
            s.append("$" + x["v"] + "$")
        elif t in ("em", "strong", "span", "link"):
            s.append(plain(x["c"]))
        elif t == "code":
            s.append(x["v"])
        elif t == "cite":
            s.append("[cite]")
        elif t == "note":
            s.append("")
    return re.sub(r"\s+", " ", "".join(s)).strip()


def find_images(node, acc):
    if isinstance(node, dict):
        if node.get("t") == "Image":
            acc.append(node["c"][2][0])
        for v in node.values():
            find_images(v, acc)
    elif isinstance(node, list):
        for v in node:
            find_images(v, acc)
    return acc


def cell_inlines(bl):
    """Aplana los bloques de una celda (párrafos, listas, divs, líneas) a inlines, sin perder texto."""
    sp = {"t": "text", "v": " "}
    out = []
    for b in bl:
        t = b["t"]
        if t in ("Plain", "Para"):
            out += inl(b["c"]) + [sp]
        elif t == "LineBlock":
            for line in b["c"]:
                out += inl(line) + [sp]
        elif t in ("BulletList", "OrderedList"):
            items = b["c"] if t == "BulletList" else b["c"][1]
            for item in items:
                out += [{"t": "text", "v": "• "}] + cell_inlines(item)
        elif t == "Div":
            out += cell_inlines(b["c"][1])
        elif t == "Table":
            for tb in b["c"][4]:
                for row in tb[3]:
                    for c in row[1]:
                        out += cell_inlines(c[4])
    return out


def cell_text(cell):
    inls = cell_inlines(cell[4])
    while inls and inls[-1] == {"t": "text", "v": " "}:
        inls.pop()
    return inls


def table_block(t):
    attr, caption, colspecs, thead, tbodies, tfoot = t["c"]
    head = [[cell_text(c) for c in row[1]] for row in thead[1]]
    hspan = [[c[3] for c in row[1]] for row in thead[1]]  # colspan de cada celda: sin él las cabeceras multicolumna se desalinean
    body, bspan = [], []
    for tb in tbodies:
        for row in tb[3]:
            body.append([cell_text(c) for c in row[1]])
            bspan.append([c[3] for c in row[1]])
    cap = []
    for b in caption[1]:
        if b["t"] in ("Plain", "Para"):
            cap += inl(b["c"])
    return {"kind": "table", "label": attr[0], "head": head, "body": body, "hspan": hspan, "bspan": bspan, "caption": cap}


def flush(seg, out):
    """Cierra un segmento de párrafo (sin espacios sobrantes en los bordes); descarta los vacíos."""
    while seg and seg[0]["t"] == "text" and seg[0]["v"].strip() == "":
        seg.pop(0)
    while seg and seg[-1]["t"] == "text" and seg[-1]["v"].strip() == "":
        seg.pop()
    if seg:
        out.append({"kind": "p", "inlines": seg})


def blocks(bl):
    out = []
    for b in bl:
        t = b["t"]
        if t == "Header":
            lvl, attr, content = b["c"]
            out.append({"kind": "h", "level": lvl, "label": attr[0], "id": attr[0], "unnumbered": "unnumbered" in attr[1], "inlines": inl(content)})
        elif t in ("Para", "Plain"):
            ins = inl(b["c"])
            # las ecuaciones de bloque que pandoc deja dentro de un párrafo pasan a ser bloques `eq` propios
            seg = []
            for x in ins:
                if x["t"] == "math" and x["display"]:
                    flush(seg, out)
                    seg = []
                    out.append({"kind": "eq", "tex": x["v"], **({"labels": x["labels"]} if x.get("labels") else {})})
                else:
                    seg.append(x)
            flush(seg, out)
        elif t == "BulletList":
            items = []
            for item in b["c"]:
                it = []
                for sb in item:
                    if sb["t"] in ("Plain", "Para"):
                        it += inl(sb["c"])
                items.append(it)
            out.append({"kind": "list", "items": items})
        elif t == "Figure":
            attr, cap, content = b["c"]
            capi = []
            for cb in cap[1]:
                if cb["t"] in ("Plain", "Para"):
                    capi += inl(cb["c"])
            imgs = find_images(content, [])
            out.append({"kind": "fig", "label": attr[0], "images": imgs, "caption": capi})
        elif t == "Table":
            out.append(table_block(b))
        elif t == "Div":
            inner = blocks(b["c"][1])
            lab = b["c"][0][0]  # el id del div envuelve a la tabla o figura: es su etiqueta
            if lab:
                for ib in inner:
                    if ib["kind"] in ("table", "fig") and not ib.get("label"):
                        ib["label"] = lab
                        break
            out += inner
        elif t == "RawBlock":
            pass
        # otros tipos: se ignoran
    return out


def text_to_inlines(txt: str):
    """Texto con $math$ -> inlines (texto por palabra, espacios como nodos, matemática como nodo)."""
    out = []
    for part in re.split(r"(\$[^$]+\$)", txt):
        if not part:
            continue
        if part.startswith("$") and part.endswith("$") and len(part) > 2:
            out.append({"t": "math", "v": part[1:-1], "display": False})
        else:
            for w in re.split(r"(\s+)", part):
                if w:
                    out.append({"t": "text", "v": " " if w.isspace() else w})
    return out


ABBREV = {"al.", "e.g.", "i.e.", "vs.", "Fig.", "Figs.", "Eq.", "Sec.", "approx.", "cf.", "No.", "etc."}


def split_sentences(inls):
    """Parte una lista de inlines en oraciones (heurística; no se pierde ningún nodo)."""
    sents, cur = [], []
    n = len(inls)
    i = 0
    while i < n:
        x = inls[i]
        cur.append(x)
        i += 1
        if x["t"] == "text" and re.search(r"[.!?][”’\")\]]*$", x["v"]) and x["v"] not in ABBREV and not re.fullmatch(r"[A-Z]\.", x["v"]):
            while i < n and inls[i]["t"] in ("note",):
                cur.append(inls[i]); i += 1
            j = i
            while j < n and inls[j]["t"] == "text" and inls[j]["v"].strip() == "":
                j += 1
            if j >= n:
                continue
            nx = inls[j]
            if nx["t"] == "text" and re.match(r"[A-Z“‘]", nx["v"]):
                cur += inls[i:j]
                sents.append(cur); cur = []
                i = j
    if cur:
        sents.append(cur)
    return sents


def bibliography(src: Path):
    refs, labels = {}, {}
    for f in list(src.glob("*.tex")) + list(src.glob("*.bbl")):
        t = f.read_text(errors="replace")
        for m in re.finditer(r"\\bibitem(?:\[([^\]]*)\])?\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})", t, re.S):
            if m.group(1):
                lab = re.sub(r"\s+", " ", m.group(1).replace("~", " ").replace("{", "").replace("}", "")).strip()
                short = re.match(r"(.*?\(\d{4}[a-z]?\))", lab)  # natbib: «Corto(año)Autores completos»
                labels[m.group(2)] = re.sub(r"\((\d{4}[a-z]?)\)", r", \1", short.group(1) if short else lab)
            s = m.group(3)
            s = re.sub(r"%.*", "", s)
            s = s.replace("\\newblock", " ")
            s = re.sub(r"\{\\(?:em|it)\s+([^{}]*)\}", r"\1", s)
            s = re.sub(r"\\(?:emph|textit|url)\{([^{}]*)\}", r"\1", s)
            s = s.replace("~", " ").replace("{", "").replace("}", "").replace("\\", "")
            refs[m.group(2)] = re.sub(r"\s+", " ", s).strip()
    return refs, labels


def author_notes(src: Path, main_tex: str) -> list:
    """Notas \\thanks{...} del bloque de autores (p. ej. contribuciones), con llaves balanceadas."""
    t = re.sub(r"(?m)^\s*%.*$", "", (src / main_tex).read_text(errors="replace"))
    out = []
    for m in re.finditer(r"\\thanks\{", t):
        i, d = m.end(), 1
        while i < len(t) and d:
            d += (t[i] == "{") - (t[i] == "}")
            i += 1
        out.append(re.sub(r"\s+", " ", t[m.end():i - 1].replace("\\samethanks", "")).strip())
    return out


def fix_captions(t: str) -> str:
    """Quita líneas en blanco dentro de \\caption{...} (válidas en LaTeX; pandoc falla o se cuelga)."""
    out, i = [], 0
    for m in re.finditer(r"\\caption(\[[^\]]*\])?\{", t):
        if m.start() < i:
            continue
        j, d = m.end(), 1
        while j < len(t) and d:
            d += (t[j] == "{") - (t[j] == "}")
            j += 1
        out.append(t[i:m.end()]); out.append(re.sub(r"\n\s*\n", " ", t[m.end():j])); i = j
    out.append(t[i:])
    return "".join(out)


def flatten_and_number(src: Path, main_tex: str, out: str = "_flat.tex") -> str:
    """Aplana \\input y numera las ecuaciones `equation` (pandoc pierde el número). Devuelve el .tex aplanado.
    Si el paper reinicia la numeración por sección (numberwithin/counterwithin) no se numera: sería falso."""
    def exists(name):
        return (src / name).exists() or (src / (name + ".tex")).exists()

    def rd(name):
        f = src / name if (src / name).exists() else src / (name + ".tex")
        t = f.read_text(errors="replace")
        t = re.sub(r"(?m)(?<!\\)%.*$", "", t)
        return re.sub(r"\\input\{([^}]+)\}", lambda m: rd(m.group(1)) if exists(m.group(1)) else m.group(0), t)

    t = fix_captions(rd(main_tex))
    if not re.search(r"\\(numberwithin|counterwithin)\{equation\}", t):
        n = [0]

        def tag(m):
            body = m.group(1)
            if re.search(r"\\(nonumber|notag|tag)\b", body):
                return m.group(0)
            n[0] += 1
            return "\\begin{equation}\\tag{%d}%s\\end{equation}" % (n[0], body)

        t = re.sub(r"\\begin\{equation\}(.*?)\\end\{equation\}", tag, t, flags=re.S)
    (src / out).write_text(t)
    return out


def add_sentences(bl):
    for b in bl:
        if b["kind"] == "p":
            b["sents"] = split_sentences(b["inlines"])


# ------------------------------------------------- bundle de un paper completo
def detect_main(src: Path) -> str:
    """Archivo .tex con \\documentclass (el de mayor tamaño si hay varios)."""
    c = [f for f in src.rglob("*.tex") if "\\documentclass" in f.read_text(errors="replace")[:5000] and not f.name.startswith("_")]
    if not c:
        sys.exit("no se encontró el .tex principal")
    return str(max(c, key=lambda f: f.stat().st_size).relative_to(src))


def build_full_paper(arxiv_id: str, main_tex: str, skip_first_div=True) -> dict:
    meta = abs_meta(arxiv_id)
    tar = cached(f"{arxiv_id}.eprint", f"https://arxiv.org/e-print/{arxiv_id}")
    src = CACHE / f"{arxiv_id}.src"
    if not src.exists():
        src.mkdir()
        with tarfile.open(tar) as tf:
            tf.extractall(src, filter="data")
    # pandoc descarta \caption dentro de figure*/table* (entornos de doble columna): se normalizan en la copia local
    for tf_ in src.rglob("*.tex"):
        t_ = tf_.read_text(errors="replace")
        t2 = re.sub(r"\\(begin|end)\{(figure|table)\*\}", r"\\\1{\2}", t_)
        if t2 != t_:
            tf_.write_text(t2)
    if main_tex == "auto":
        main_tex = detect_main(src)
    main_tex = flatten_and_number(src, main_tex)
    ast_path = CACHE / f"{arxiv_id}.pandoc.json"
    res = None
    for fmt in ("latex", "latex-latex_macros"):  # 2.ª estrategia: sin expansión de macros (evita bucles)
        try:
            res = subprocess.run(["pandoc", main_tex, "-f", fmt, "-t", "json", "-o", str(ast_path)], cwd=src, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            print(f"  pandoc se colgó con -f {fmt}; se reintenta")
            continue
        if res.returncode == 0:
            break
        print(f"  pandoc falló con -f {fmt}: {res.stderr[:120]}")
    if res is None or res.returncode != 0:
        sys.exit(f"pandoc no pudo convertir {arxiv_id}")
    ast = json.loads(ast_path.read_text())
    bl = blocks(ast["blocks"])
    # el primer bloque es un aviso de licencia de Google, lo mostramos aparte
    notice = None
    if bl and bl[0]["kind"] == "p" and "Provided proper attribution" in plain(bl[0]["inlines"]):
        notice = plain(bl[0]["inlines"])
        bl = bl[1:]
    bl.insert(0, {"kind": "p", "abs": True, "inlines": text_to_inlines(meta["abstract"])})
    add_sentences(bl)
    # ids estables
    for i, b in enumerate(bl):
        b["id"] = f"b{i}"
    # imágenes: copiar a public/
    dest = OUT / arxiv_id
    dest.mkdir(parents=True, exist_ok=True)
    for b in bl:
        if b["kind"] == "fig":
            files = []
            for im in b["images"]:
                base = Path(im).name
                cand = [src / im] + [src / (im + e) for e in (".png", ".jpg", ".jpeg", ".pdf")]
                if not any(c.exists() and c.is_file() for c in cand):  # \\graphicspath: se busca por nombre en todo el árbol
                    cand = [f for e in ("", ".png", ".jpg", ".jpeg", ".pdf") for f in src.rglob(base + e) if f.is_file()]
                f = next((c for c in cand if c.exists() and c.is_file()), None)
                if f and f.suffix == ".pdf":
                    # figura vectorial en PDF -> PNG (pdftocairo), para poder mostrarla en el navegador
                    subprocess.run(["pdftocairo", "-png", "-singlefile", "-r", "110", str(f), str(dest / f.stem)], check=True)
                    files.append(f"/papers/{arxiv_id}/{f.stem}.png")
                elif f:
                    shutil.copy(f, dest / f.name)
                    files.append(f"/papers/{arxiv_id}/{f.name}")
            b["images"] = files
    # referencias del paper: se guardan como texto simple para el tooltip de citas
    return {
        "arxivId": arxiv_id,
        "title": meta["title"],
        "authors": meta["authors"],
        "date": meta["date"],
        "abstract": meta["abstract"],
        "license": notice,
        "authorNotes": author_notes(src, main_tex),
        "full": True,
        "refs": (bib := bibliography(src))[0],
        "refLabels": bib[1],
        "blocks": bl,
    }


def build_abstract_paper(arxiv_id: str) -> dict:
    meta = abs_meta(arxiv_id)
    meta["full"] = False
    ins = text_to_inlines(meta["abstract"])
    meta["blocks"] = [{"kind": "p", "id": "b0", "inlines": ins}]
    add_sentences(meta["blocks"])
    meta["refs"] = {}
    return meta


# ------------------------------------------------------------ anclas por cita
def block_plain(b) -> str:
    k = b["kind"]
    if k in ("p", "h"):
        return plain(b["inlines"])
    if k == "eq":
        return "$" + b["tex"] + "$"
    if k == "list":
        return " ".join(plain(i) for i in b["items"])
    if k == "fig":
        return plain(b["caption"])
    if k == "table":
        return plain(b["caption"])
    return ""


def note_texts(b):
    """Texto de las notas al pie dentro de un bloque."""
    res = []

    def walk(inls):
        for x in inls:
            if x["t"] == "note":
                for nb in x["blocks"]:
                    if nb["kind"] == "p":
                        res.append(plain(nb["inlines"]))
            elif "c" in x and isinstance(x["c"], list):
                walk(x["c"])

    if b["kind"] in ("p", "h"):
        walk(b["inlines"])
    return res


def resolve(paper: dict, quote: str, what: str) -> dict:
    hits = []
    for b in paper["blocks"]:
        if quote in block_plain(b):
            hits.append({"blockId": b["id"], "where": "block", "abs": bool(b.get("abs"))})
        for nt in note_texts(b):
            if quote in nt:
                hits.append({"blockId": b["id"], "where": "note"})
    if len(hits) > 1 and sum(h["abs"] for h in hits) == 1:  # frase del abstract que reaparece en el texto: vale el abstract
        hits = [h for h in hits if h["abs"]]
    hits = [{k: v for k, v in h.items() if k != "abs"} for h in hits]
    if len(hits) != 1:
        sys.exit(f"ANCLA INVÁLIDA ({what}): la cita aparece {len(hits)} veces en {paper['arxivId']}: «{quote[:90]}»")
    return {"quote": quote, **hits[0]}


def check_refkeys(node, papers: dict, ctx: str):
    """Relaciones `bibliografia`: la clave debe existir en la bibliografía real del paper citante."""
    if isinstance(node, dict):
        if "refKey" in node and node["refKey"] not in papers[node["paper"]].get("refs", {}):
            sys.exit(f"RELACIÓN INVÁLIDA ({ctx}): {node['refKey']} no está en la bibliografía de {node['paper']}")
        for v in node.values():
            check_refkeys(v, papers, ctx)
    elif isinstance(node, list):
        for v in node:
            check_refkeys(v, papers, ctx)


def resolve_all(node, papers: dict, ctx: str, path=""):
    """Recorre el contenido curado y resuelve todo objeto con 'quote' y 'paper'."""
    if isinstance(node, dict):
        if "quote" in node and "paper" in node:
            node["anchor"] = resolve(papers[node["paper"]], node["quote"], f"{ctx}:{path}")
        for k, v in node.items():
            resolve_all(v, papers, ctx, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            resolve_all(v, papers, ctx, f"{path}[{i}]")


def main():
    spec = json.loads((CONTENT / "papers.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    papers = {}
    for p in spec["papers"]:
        print(f"== {p['id']}")
        if p.get("main_tex"):
            papers[p["id"]] = build_full_paper(p["id"], p["main_tex"])
        else:
            papers[p["id"]] = build_abstract_paper(p["id"])
        (OUT / f"{p['id']}.json").write_text(json.dumps(papers[p["id"]], ensure_ascii=False))
    # contenido curado: se resuelven las anclas por cita
    resolved = {}
    for f in sorted(CONTENT.glob("*.json")):
        if f.name == "papers.json":
            continue
        data = json.loads(f.read_text())
        resolve_all(data, papers, f.name)
        check_refkeys(data, papers, f.name)
        resolved[f.stem] = data
    (OUT / "_content.json").write_text(json.dumps(resolved, ensure_ascii=False))
    n_full = sum(1 for p in papers.values() if p["full"])
    print(f"listo: {len(papers)} papers ({n_full} completos), {len(resolved)} archivos de contenido")


if __name__ == "__main__":
    main()
