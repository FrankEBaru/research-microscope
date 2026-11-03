#!/usr/bin/env python3
"""Local offline fixture for Attention Is All You Need (arXiv 1706.03762).

Downloads the e-print from arXiv (not Modal, not Meta), parses it with the
reader, and writes a directory ``rrm.offline`` can serve. The paper text stays
out of git (``offline-fixtures-attention/``).

The license row keeps the arXiv non-exclusive URL, which the live gate treats
as closed. ``fixture_open`` is honored only when ``RRM_LICENSE_FIXTURE=1``.

    python3 scripts/build_attention_fixture.py --out offline-fixtures-attention
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import tarfile
import urllib.request
from pathlib import Path

from rrm.reader.latex import materialize_figures, parse_tree, plain, stats

ARXIV = "1706.03762"
CID = 13756489
QUESTION = "attention"
SLUG = "attention"
ASK = "The Transformer is based solely on attention and dispenses with recurrence."
LICENSE = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
EPRINT = "https://arxiv.org/e-print/1706.03762"
ABS = "https://export.arxiv.org/api/query?id_list=1706.03762"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "research-microscope-rrm81/0.1"})
    with urllib.request.urlopen(req, timeout=120) as res:
        return res.read()


def _version() -> str:
    try:
        xml = _get(ABS).decode("utf-8", "replace")
    except Exception:
        return "v7"
    match = re.search(r"1706\.03762(v\d+)", xml)
    return match.group(1) if match else "v7"


def _unpack(blob: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    raw = blob
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tar:
            _extract(tar, dest)
            return
    except tarfile.TarError:
        pass
    if blob[:2] == b"\x1f\x8b":
        raw = gzip.decompress(blob)
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tar:
            _extract(tar, dest)
            return
    raise SystemExit("the e-print is not a tar archive")


def _extract(tar: tarfile.TarFile, dest: Path) -> None:
    root = dest.resolve()
    for member in tar.getmembers():
        if member.issym() or member.islnk():
            continue
        target = (dest / member.name).resolve()
        if root != target and root not in target.parents:
            raise SystemExit(f"e-print path escapes the cache: {member.name}")
        tar.extract(member, dest, set_attrs=False)


def _write(path: Path, body) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False) + "\n", encoding="utf-8")


def _sentences(paper: dict) -> list[tuple[str, str]]:
    section = ""
    out = []
    for block in paper.get("blocks") or []:
        if block.get("kind") == "h":
            section = plain(block.get("inlines") or [])
        if block.get("kind") != "p":
            continue
        for sent in block.get("sents") or []:
            text = plain(sent)
            if len(text) > 40:
                out.append((section, text))
    return out


def _find(rows, needle: str) -> tuple[str, str]:
    low = needle.lower()
    for section, text in rows:
        if low in text.lower():
            return section, text
    raise SystemExit(f"the parsed paper has no sentence containing {needle!r}")


def _claim(text: str, cite: str, section: str, part: str) -> dict:
    row = {"text": text, "cite": cite, "paper_id": str(CID), "section": section}
    if part != "sin_respaldo":
        row["verified"] = True
    return row


def _ask(rows) -> dict:
    sole_sec, sole = _find(rows, "based solely on attention")
    rec_sec, rec = _find(rows, "dispens")
    scale_sec, scale = _find(rows, "scale the dot products")
    return {
        "extracts": [
            {"paper": CID, "section": sole_sec, "text": sole},
            {"paper": CID, "section": rec_sec, "text": rec},
        ],
        "papers": 1,
        "line": "",
        "empty": False,
        "matched": 2,
        "parts": {
            "coincide": [_claim(
                "The Transformer is based solely on attention mechanisms.",
                sole, sole_sec, "coincide",
            )],
            "contradice": [_claim(
                "Recurrence remains the core of the model.",
                rec, rec_sec, "contradice",
            )],
            "sin_respaldo": [{"text": "Nothing in these sentences says the model was trained on images."}],
            "te_falto": [_claim(
                "The dot products are scaled.",
                scale, scale_sec, "te_falto",
            )],
        },
        "note": "",
        "meta": {"source": "rrm-81-fixture", "model": ""},
        "store": {"ready": 1, "total": 1},
    }


def build(out: Path, cache: Path) -> dict:
    src = cache / "src"
    blob_path = cache / "eprint.tar.gz"
    if not (src / "ms.tex").is_file() and not any(src.rglob("*.tex")):
        if not blob_path.is_file():
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(_get(EPRINT))
        if src.exists():
            import shutil
            shutil.rmtree(src)
        _unpack(blob_path.read_bytes(), src)
    parsed = parse_tree(src, arxiv_id=ARXIV)
    paper = parsed.get("paper")
    if not isinstance(paper, dict):
        raise SystemExit(f"parse failed: {parsed.get('reason') or parsed.get('route')}")
    fig_dir = cache / "figures"
    if fig_dir.exists():
        import shutil
        shutil.rmtree(fig_dir)
    rendered = materialize_figures(paper["blocks"], src, fig_dir)
    version = _version()
    paper["corpusid"] = CID
    paper["arxivId"] = ARXIV
    paper["full"] = True
    paper["stage"] = "full"
    paper["source"] = "latex"
    counts = stats(paper)
    counts["figures_rendered"] = rendered
    doc = {
        "status": "done",
        "meta": {
            "corpusid": CID,
            "arxiv": ARXIV,
            "status": "done",
            "stage": "full",
            "source": "latex",
            "reason": None,
            "stages": {"stub": "done", "sections": "done", "figures": "done", "crops": "skipped"},
        },
        "paper": paper,
    }
    if out.exists():
        import shutil
        shutil.rmtree(out)
    _write(out / "manifest.json", {
        "version": 2,
        "queries": [{
            "slug": SLUG,
            "q": QUESTION,
            "paper_ids": [CID],
            "saved_papers": [CID],
            "panorama_mode": "sim",
            "panorama_fallback": True,
        }],
    })
    _write(out / "burst" / f"{SLUG}.json", {
        "query": QUESTION,
        "mode": "short",
        "papers": [{
            "corpusid": CID,
            "title": paper.get("title") or "Attention Is All You Need",
            "year": 2017,
            "venue": "NIPS",
            "authors": paper.get("authors") or [],
            "score": 1,
            "is_cs": True,
        }],
        "similar": [],
        "edges": [],
        "subtopics": [],
    })
    _write(out / "labels" / f"{SLUG}.json", {
        "ok": True, "reason": "", "note": "", "survey_paper": None,
        "by_id": {str(CID): {
            "abstract": paper.get("abstract") or "",
            "authors": paper.get("authors") or [],
            "tldr": "",
            "survey": False,
            "retracted": False,
            "retraction": "",
        }},
    })
    _write(out / "status" / f"{SLUG}.json", {
        "papers": [{"id": CID, "status": "done", "source": "latex", "stage": "full", "reason": None, "text": True}],
    })
    _write(out / "papers" / f"{CID}.json", doc)
    files = out / "files" / str(CID)
    files.mkdir(parents=True, exist_ok=True)
    for png in fig_dir.glob("*"):
        if png.is_file():
            (files / png.name).write_bytes(png.read_bytes())
    _write(out / "licenses.json", {
        "_source": (
            "RRM-81 offline fixture. fixture_open does nothing unless RRM_LICENSE_FIXTURE=1. "
            "Do not copy fixture_open into the live license map."
        ),
        ARXIV: {
            "license": LICENSE,
            "version": version,
            "corpusid": CID,
            "fixture_open": True,
        },
    })
    answer = _ask(_sentences(paper))
    _write(out / "ask" / "index.json", [
        {"focus": str(CID), "text": ASK, "stage": "frases", "file": "frases.json"},
        {"focus": str(CID), "text": ASK, "stage": "revisar", "file": "revisar.json"},
    ])
    _write(out / "ask" / "frases.json", answer)
    _write(out / "ask" / "revisar.json", answer)
    _write(out / "build-report.json", {"arxiv": ARXIV, "corpusid": CID, "version": version, **counts})
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the local Attention offline fixture from the arXiv e-print.")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--out", type=Path, default=root / "offline-fixtures-attention")
    parser.add_argument("--cache", type=Path, default=root / "offline-fixtures.cache" / "attention")
    args = parser.parse_args(argv)
    counts = build(args.out, args.cache)
    print(json.dumps({"out": str(args.out), **counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
