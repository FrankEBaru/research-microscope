#!/usr/bin/env python3
"""Write a synthetic fixture tar for scripts/check.sh. Does not upload."""

import json
import struct
import tarfile
import tempfile
import zlib
from pathlib import Path

BLOCKS = [
    {"id": "b0", "kind": "h", "level": 1, "inlines": [{"t": "text", "v": "Intro"}]},
    {
        "id": "b1",
        "kind": "p",
        "inlines": [
            {"t": "text", "v": "See "},
            {"t": "ref", "label": "eq:a", "number": 1, "target": "b2"},
        ],
    },
    {"id": "b2", "kind": "eq", "tex": "y = x", "number": 1, "labels": ["eq:a"]},
    {"id": "b3", "kind": "fig", "caption": [{"t": "text", "v": "Plot"}]},
]


def _png() -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    scan = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", scan) + chunk(b"IEND", b"")


def _paper(stage: str, images: list) -> dict:
    blocks = []
    for block in BLOCKS:
        row = dict(block)
        if row["kind"] == "fig":
            row["images"] = list(images)
        blocks.append(row)
    return {"stage": stage, "blocks": blocks}


def main() -> None:
    dest = Path("/tmp/demo-fixtures.tar.gz")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "paper_stub.json").write_text(
            json.dumps({"stage": "stub", "blocks": [{"id": "b0", "kind": "p", "abs": True}]}),
            encoding="utf-8",
        )
        (root / "paper_sections.json").write_text(
            json.dumps(_paper("sections", ["figures/plot.pdf"])),
            encoding="utf-8",
        )
        (root / "paper_figures.json").write_text(
            json.dumps(_paper("figures", ["plot.png"])),
            encoding="utf-8",
        )
        (root / "plot.png").write_bytes(_png())
        (root / "burst.json").write_text(
            json.dumps({
                "mode": "short",
                "papers": [
                    {"corpusid": 1, "title": "Alpha", "year": 2020, "venue": "Venue", "citationcount": 3},
                    {"corpusid": 2, "title": "Beta", "year": 2021, "venue": "Venue", "citationcount": 2},
                    {"corpusid": 3, "title": "Gamma", "year": 2022, "venue": "Venue", "citationcount": 1},
                ],
                "edges": [{"citing": 1, "cited": 2}, {"citing": 2, "cited": 3}],
                "subtopics": [],
            }),
            encoding="utf-8",
        )
        with tarfile.open(dest, "w:gz") as tar:
            for path in sorted(root.iterdir()):
                tar.add(path, arcname=path.name)
    print(dest)


if __name__ == "__main__":
    main()
