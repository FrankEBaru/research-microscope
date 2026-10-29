#!/usr/bin/env python3
"""Descarga los papers de ejemplo desde arXiv y construye los bundles que lee la UI.

- Los datos descargados NO se commitean (repo público; ver AGENTS.md): salen en
  `public/papers/` y `.cache/`, ambos en .gitignore. Se regeneran con `npm run data`.
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
            out.append({"t": "math", "v": tex, "display": kind["t"] == "DisplayMath"})
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


def cell_text(cell):
    bl = cell[4]
    inls = []
    for b in bl:
        if b["t"] in ("Plain", "Para"):
            inls += inl(b["c"]) + [{"t": "text", "v": " "}]
    while inls and inls[-1] == {"t": "text", "v": " "}:
        inls.pop()
    return inls


def table_block(t):
    attr, caption, colspecs, thead, tbodies, tfoot = t["c"]
    head = [[cell_text(c) for c in row[1]] for row in thead[1]]
    body = []
    for tb in tbodies:
        for row in tb[3]:
            body.append([cell_text(c) for c in row[1]])
    cap = []
    for b in caption[1]:
        if b["t"] in ("Plain", "Para"):
            cap += inl(b["c"])
    return {"kind": "table", "label": attr[0], "head": head, "body": body, "caption": cap}


def blocks(bl):
    out = []
    for b in bl:
        t = b["t"]
        if t == "Header":
            lvl, attr, content = b["c"]
            out.append({"kind": "h", "level": lvl, "id": attr[0], "unnumbered": "unnumbered" in attr[1], "inlines": inl(content)})
        elif t in ("Para", "Plain"):
            ins = inl(b["c"])
            if len(ins) == 1 and ins[0]["t"] == "math" and ins[0]["display"]:
                out.append({"kind": "eq", "tex": ins[0]["v"]})
            else:
                out.append({"kind": "p", "inlines": ins})
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
            out += blocks(b["c"][1])
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


def bibliography(src: Path) -> dict:
    refs = {}
    for f in src.glob("*.tex"):
        t = f.read_text(errors="replace")
        for m in re.finditer(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})", t, re.S):
            s = m.group(2)
            s = re.sub(r"%.*", "", s)
            s = s.replace("\\newblock", " ")
            s = re.sub(r"\{\\(?:em|it)\s+([^{}]*)\}", r"\1", s)
            s = re.sub(r"\\(?:emph|textit|url)\{([^{}]*)\}", r"\1", s)
            s = s.replace("~", " ").replace("{", "").replace("}", "").replace("\\", "")
            refs[m.group(1)] = re.sub(r"\s+", " ", s).strip()
    return refs


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


def add_sentences(bl):
    for b in bl:
        if b["kind"] == "p":
            b["sents"] = split_sentences(b["inlines"])


# ------------------------------------------------- bundle de un paper completo
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
    ast_path = CACHE / f"{arxiv_id}.pandoc.json"
    res = subprocess.run(
        ["pandoc", main_tex, "-f", "latex", "-t", "json", "-o", str(ast_path)],
        cwd=src, capture_output=True, text=True,
    )
    if res.returncode != 0:
        sys.exit(f"pandoc falló para {arxiv_id}: {res.stderr[:400]}")
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
                cand = [src / im] + [src / (im + e) for e in (".png", ".jpg", ".jpeg", ".pdf")]
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
        "refs": bibliography(src),
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
            hits.append({"blockId": b["id"], "where": "block"})
        for nt in note_texts(b):
            if quote in nt:
                hits.append({"blockId": b["id"], "where": "note"})
    if len(hits) != 1:
        sys.exit(f"ANCLA INVÁLIDA ({what}): la cita aparece {len(hits)} veces en {paper['arxivId']}: «{quote[:90]}»")
    return {"quote": quote, **hits[0]}


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
        resolved[f.stem] = data
    (OUT / "_content.json").write_text(json.dumps(resolved, ensure_ascii=False))
    n_full = sum(1 for p in papers.values() if p["full"])
    print(f"listo: {len(papers)} papers ({n_full} completos), {len(resolved)} archivos de contenido")


if __name__ == "__main__":
    main()
