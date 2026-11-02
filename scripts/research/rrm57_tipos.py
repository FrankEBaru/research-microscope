#!/usr/bin/env python3
"""Cuenta tipos de artefacto y de hueco. Sin red. Uso: rrm57_tipos.py DIR"""

import collections
import json
import re
import sys

EASY = re.compile(
    r"it is easy to (?:see|show|check|verify)|straightforward to (?:check|show|verify)|"
    r"we omit the (?:proof|coefficient|details)|one can (?:show|verify) that|"
    r"it can be shown that|without loss of generality",
    re.I,
)
ASSUME = re.compile(
    r"we assume that|assume that|assuming that|suppose that|"
    r"under the assumption that|without loss of generality",
    re.I,
)
ATAJO = re.compile(
    r"residual connection|shortcut connection|skip connections|cropped feature map",
    re.I,
)
SHAPE = re.compile(r"\\mathbb\s*\{\s*R\s*\}\s*\^\{([^{}]+)\}")


def flat(text):
    return re.sub(r"\s+", "", text or "")


def clip(text, n=180):
    return re.sub(r"\s+", " ", text or "").strip()[:n]


def load(path):
    out = []
    for name in sorted(__import__("os").listdir(path)):
        if name.endswith(".json"):
            with open(f"{path}/{name}", encoding="utf-8") as handle:
                out.append(json.load(handle))
    return out


def barras(latex):
    text = flat(latex)
    if re.search(r"softmax", text, re.I):
        return True
    return "\\exp" in text and "\\sum" in text and "\\frac" in text


def escala(latex):
    text = flat(latex)
    low = text.lower()
    if "softmax" in low and "\\sqrt" in text:
        return True
    if "\\exp" in text and "\\sqrt" in text and re.search(r"d[_}]|/\\sqrt|\\sqrt\{d", text):
        return True
    return bool(re.search(r"\\over\\sigma|/\sigma", text) and "\\mu" in text)


def rejilla(latex):
    text = flat(latex)
    if re.search(r"(?:sin|cos)\(pos/", text):
        return True
    return bool(re.search(r"(?:sin|cos)\\frac\{[^{}]{0,80}", text) and re.search(r"k", text) and re.search(r"n", text))


def casos(latex):
    if "\\begin{cases}" in (latex or ""):
        return True
    return "\\begin{array}" in (latex or "") and bool(re.search(r"\\(?:text|mbox|mathrm)\{if\b", latex or ""))


def campo(latex):
    text = flat(latex)
    if re.search(r"\\dot\{|\\ddot\{", text):
        return True
    return "\\frac{d" in text and "{dt}" in text


def objetivo(latex):
    text = flat(latex)
    if re.search(r"arg\\[,!]?\\?min|\\argmin", text):
        return True
    return "s.t." in (latex or "") and bool(re.search(r"\\min|text\{min", text))


def curva(latex, prose):
    text = flat(latex)
    if "\\sum" in text or "=" not in text:
        return ""
    if "\\ln" in text and "0.5" in text:
        return "logit"
    if "\\exp" in text and "\\sigma" in text and "\\approx" in (prose or ""):
        return "gauss"
    if "\\exp" in text and "\\gamma" in text and re.search(r"set to\s*\$?10\b", prose or ""):
        return "agenda"
    if "warmup" in text and "\\min" in text and "4000" in (prose or ""):
        return "tasa"
    return ""


def math_near(text, match, span=70):
    window = text[max(0, match.start() - span): match.end() + span]
    return "$" in window or "\\" in window


def add(bucket, paper, row, quote):
    bucket.append((paper["corpusid"], (row.get("section") or "")[:42], row.get("id") or "", clip(quote)))


def main():
    papers = load(sys.argv[1])
    hits = collections.defaultdict(list)
    for doc in papers:
        paper = doc["paper"]
        rows = doc["rows"]
        by_sec = collections.defaultdict(list)
        for row in rows:
            latex, prose = row.get("latex") or "", row.get("text") or ""
            if row.get("kind") == "eq":
                by_sec[row.get("section") or ""].append(row)
                if barras(latex):
                    add(hits["barras"], paper, row, latex)
                if escala(latex):
                    add(hits["escala"], paper, row, latex)
                if rejilla(latex):
                    add(hits["rejilla"], paper, row, latex)
                if casos(latex):
                    add(hits["casos"], paper, row, latex)
                if campo(latex):
                    add(hits["campo"], paper, row, latex)
                if objetivo(latex):
                    add(hits["objetivo"], paper, row, latex)
                kind = curva(latex, prose)
                if kind:
                    add(hits["curva"], paper, row, kind + " " + latex)
            found_shape = SHAPE.search(latex) or SHAPE.search(prose)
            if found_shape:
                add(hits["forma"], paper, row, found_shape.group(0))
                if re.search(r"\\times|\d|\+", found_shape.group(1)):
                    add(hits["forma_compuesta"], paper, row, found_shape.group(0))
            if "\\begin{algorithm}" in prose or "\\begin{algorithm}" in latex:
                add(hits["pasos"], paper, row, prose or latex)
            if ATAJO.search(prose):
                add(hits["atajo"], paper, row, prose[max(0, ATAJO.search(prose).start() - 40):])
            found = EASY.search(prose)
            if found and math_near(prose, found):
                add(hits["salto"], paper, row, prose[max(0, found.start() - 30): found.end() + 90])
            found = ASSUME.search(prose)
            if found and math_near(prose, found):
                add(hits["supuesto"], paper, row, prose[max(0, found.start() - 20): found.end() + 100])
        for group in by_sec.values():
            blob = " ".join(flat(row.get("latex") or "") for row in group)
            if len(group) > 6 or any(escala(row.get("latex") or "") for row in group):
                continue
            low = blob.lower()
            if ("softmax" in low or ("\\exp" in blob and "\\sum" in blob)) and "\\sqrt" in blob and re.search(r"d[_z}]", blob):
                host = next(row for row in group if "\\sqrt" in flat(row.get("latex") or ""))
                add(hits["escala"], paper, host, host.get("latex") or "")
    print("papers", len(papers))
    for name in (
        "barras", "escala", "rejilla", "casos", "forma", "forma_compuesta", "campo",
        "objetivo", "pasos", "curva", "atajo", "salto", "supuesto",
    ):
        rows = hits[name]
        ids = sorted({item[0] for item in rows})
        print(f"\n## {name} papers={len(ids)} hits={len(rows)}")
        print("ids", ",".join(str(item) for item in ids))
        seen = set()
        for item in rows:
            if item[0] in seen:
                continue
            seen.add(item[0])
            print(f"{item[0]}\t{item[1]}\t{item[3]}")


if __name__ == "__main__":
    main()
