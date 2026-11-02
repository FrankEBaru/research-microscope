"""Entrypoints de Modal para RRM-55. No se ejecutan desde los tests.

Cada etapa exige `RRM_PASSAGES_STAGE` igual al nombre de la etapa. Franklin
la da una por una. El tope en dólares, si lo fija, va en
`RRM_PASSAGES_BUDGET_USD`. Sin esa variable no hay un tope inventado.

Estimados [I], CPU y L4 solamente, tarifas del 2026-10-28 en
`rrm/passages/cost.py`. La memoria no está en esa tarifa.

    RRM_PASSAGES_STAGE=e0 modal run rrm/passages/app.py::e0
    RRM_PASSAGES_STAGE=e1 modal run rrm/passages/app.py::e1
    RRM_PASSAGES_STAGE=e2 modal run rrm/passages/app.py::e2
    RRM_PASSAGES_STAGE=e3 modal run rrm/passages/app.py::e3
    RRM_PASSAGES=1 RRM_PASSAGES_STAGE=e4 modal run rrm/search/serve.py::passages_query --symbol '\\sqrt{d_k}'

E0 lee el grafo que ya está en el volumen. No baja e-prints.
E1 baja 5, E2 llega a 50 y mide el embed, E3 completa 2,000.
E4 consulta desde BurstSearch, que carga `passages/` solo con el flag.
Al terminar, Modal queda parado: estas funciones no dejan un contenedor caliente.
`RRM_PASSAGES_IGNORE_STOP=1` sigue después de un top parecido a las citas globales.
`RRM_PASSAGES_BREAK_LOCK=1` levanta un harvest.lock viejo. Una sola máquina.
"""

import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 2:
    ROOT = _HERE.parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

import modal

from rrm.passages.cost import stage_estimate

MOUNT = "/s2"
RELEASE = "2026-10-20"
CPU_USD_PER_CORE_S = 0.0000131

cpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy", "pyarrow")
    .add_local_python_source("rrm")
)
index_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", extra_index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters", "sentencepiece")
    .add_local_python_source("rrm")
)
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch")
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters", "sentencepiece")
    .add_local_python_source("rrm")
)

app = modal.App("rrm-passages")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)

# Modal no pasa el entorno local al contenedor. Estas variables viajan como
# Secret.from_dict, tomadas del shell que lanza `modal run`. No son claves.
_STAGE_KEYS = (
    "RRM_PASSAGES_STAGE",
    "RRM_PASSAGES_BUDGET_USD",
    "RRM_PASSAGES_IGNORE_STOP",
    "RRM_PASSAGES_BREAK_LOCK",
    "RRM_PASSAGES_ANCHORS",
    "RRM_ARXIV_CONTACT",
)
stage_env = modal.Secret.from_dict({key: os.environ[key] for key in _STAGE_KEYS if os.environ.get(key)})


def _require(stage):
    allowed = os.environ.get("RRM_PASSAGES_STAGE", "").strip()
    if allowed != stage:
        raise SystemExit(
            f"{stage} no corre sin RRM_PASSAGES_STAGE={stage}. Franklin da el permiso por etapa."
        )


def _budget():
    raw = os.environ.get("RRM_PASSAGES_BUDGET_USD", "").strip()
    if not raw:
        return None
    return float(raw)


def _root():
    return Path(MOUNT) / RELEASE


def _passages():
    return _root() / "passages"


def _report(stage, started, *, cpu, gpu_l4_seconds=0, extra=None):
    elapsed = round(time.time() - started, 3)
    body = {
        "stage": stage,
        "seconds": elapsed,
        "usd_cpu_est": elapsed * cpu * CPU_USD_PER_CORE_S,
        "usd_note": "[I] CPU de rrm/reader/serve.py; la memoria no entra. No es el costo medido de Modal.",
        "plan": stage_estimate(stage),
    }
    if gpu_l4_seconds:
        body["gpu_l4_seconds"] = gpu_l4_seconds
    if extra:
        body.update(extra)
    print(json.dumps(body, ensure_ascii=False), flush=True)
    return body


def _load_graph():
    import numpy as np

    from rrm.search.graph import Graph

    dest = _root() / "index_ext"
    return Graph(
        np.load(dest / "graph_ids.npy", mmap_mode="r"),
        np.load(dest / "out_indptr.npy", mmap_mode="r"),
        np.load(dest / "out_indices.npy", mmap_mode="r"),
        np.load(dest / "in_indptr.npy", mmap_mode="r"),
        np.load(dest / "in_indices.npy", mmap_mode="r"),
    )


def _neighbors(index, faiss_ids, anchor, k):
    from rrm.search.faissutil import search_vectors, vector_at

    vec = vector_at(index, faiss_ids, int(anchor))
    if vec is None:
        return []
    hits = search_vectors(index, faiss_ids, vec, int(k) + 1)
    return [cid for cid, _dist in hits if int(cid) != int(anchor)][: int(k)]


@app.function(image=index_image, volumes={MOUNT: vol}, secrets=[stage_env], cpu=2, memory=32768, timeout=1800, max_containers=1)
def e0_run():
    """Tres vecindarios. Solo lectura. Escribe passages/e0.json."""
    _require("e0")
    import numpy as np

    from rrm.passages.cut import THEMES, apply_anchor_overrides, cut_flags, resolve_seeds, theme_report
    from rrm.passages.meta import meta_from_files
    from rrm.search.display import PaperLookup
    from rrm.search.encode import QueryEncoder
    from rrm.search.store import load_display, load_faiss

    started = time.time()
    root = _root()
    graph = _load_graph()
    meta = np.load(root / "index_ext" / "node_meta.npz", mmap_mode="r", allow_pickle=True)
    cc = np.maximum(np.asarray(meta["cc"]), 0)
    field = np.asarray(meta["field"])
    names = np.asarray(meta["field_names"])
    index, faiss_ids = load_faiss(root / "index")
    display = load_display(root / "index")
    lookup = PaperLookup(display)
    encoder = None

    def title_hit(title):
        return lookup.resolve(title)

    def first_hit(question):
        nonlocal encoder
        if encoder is None:
            encoder = QueryEncoder()
            encoder.load()
        # El índice guarda título+abstract con proximidad. La pregunta del tema
        # se embebe en ese mismo espacio; el burst corto sigue en adhoc.
        vec = encoder.encode_proximity([question])[0]
        from rrm.search.faissutil import search_vectors

        hits = search_vectors(index, faiss_ids, vec, 1)
        return hits[0][0] if hits else None

    themes = apply_anchor_overrides(THEMES, os.environ.get("RRM_PASSAGES_ANCHORS", ""))
    reports = []
    display_path = root / "index" / "display.parquet"
    ext_path = root / "index_ext" / "display_ext.parquet"

    def meta_of(cid):
        return meta_from_files(cid, display_path, ext_path)

    def text_neighbors(text):
        nonlocal encoder
        if encoder is None:
            encoder = QueryEncoder()
            encoder.load()
        from rrm.search.faissutil import search_vectors

        vec = encoder.encode_proximity([text.strip() + "\n"])[0]
        return [cid for cid, _dist in search_vectors(index, faiss_ids, vec, 201)]

    def text_of(cid):
        # Solo el título: display no trae abstract. El vector de papers es título+abstract.
        return ((meta_of(cid) or {}).get("title") or "").strip()

    for spec in themes:
        seeds = resolve_seeds(
            spec,
            neighbors_of=lambda anchor: _neighbors(index, faiss_ids, anchor, 200),
            first_hit=first_hit,
            title_hit=title_hit,
            text_neighbors=text_neighbors,
            text_of=text_of,
        )
        if not seeds["seeds"]:
            reports.append({**seeds, "top": [], "by_citations": [], "ranked_ids": [], "same_order": False, "overlap": 0})
            continue
        report = theme_report(graph, cc, seeds["seeds"], meta_of, field=field, field_names=names)
        report.update({key: seeds.get(key) for key in ("name", "anchor", "seeds", "neighbors", "how", "via", "error")})
        report["seeds"] = len(seeds["seeds"])
        reports.append(report)

    flags = cut_flags(reports)
    body = {"themes": reports, **flags, "quota_note": "cupos parejos [I] si no hay burst_counts.json"}
    dest = _passages()
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "e0.json").write_text(json.dumps(body), encoding="utf-8")
    vol.commit()
    return _report("e0", started, cpu=2, extra={
        "stop": flags["stop"], "close": flags["close"], "errors": flags["errors"], "themes": len(reports),
        "via": {item.get("name"): item.get("via") for item in reports},
        "neighbors": {item.get("name"): item.get("neighbors") for item in reports},
    })


@app.function(image=cpu_image, volumes={MOUNT: vol}, secrets=[stage_env], cpu=1, memory=2048, timeout=8 * 3600, max_containers=1)
def harvest_run(stage: str, n: int):
    """Baja y parsea los primeros `n` de la unión. Reanudable. Sin GPU."""
    _require(stage)
    from rrm.passages.arxiv import ArxivClient, ArxivStopped
    from rrm.passages.cost import over_budget
    from rrm.passages.cut import union_from_reports
    from rrm.passages.harvest import StageBudget, harvest_ids
    from rrm.passages.meta import meta_from_files
    from rrm.passages.store import compile_store

    started = time.time()
    dest = _passages()
    e0_path = dest / "e0.json"
    if not e0_path.is_file():
        raise SystemExit("falta passages/e0.json; E0 no corrió")
    e0 = json.loads(e0_path.read_text(encoding="utf-8"))
    ignore = os.environ.get("RRM_PASSAGES_IGNORE_STOP") == "1"
    if (e0.get("stop") or e0.get("close") or e0.get("errors")) and not ignore:
        raise SystemExit(
            "E0 marcó stop, close o temas sin semillas "
            f"(errors={e0.get('errors')}). No se bajan e-prints. RRM_PASSAGES_IGNORE_STOP=1 si Franklin sigue."
        )
    counts_path = dest / "burst_counts.json"
    counts = None
    if counts_path.is_file():
        raw_counts = json.loads(counts_path.read_text(encoding="utf-8"))
        if isinstance(raw_counts, dict):
            counts = [raw_counts.get(item.get("name")) for item in e0.get("themes") or []]
        else:
            counts = raw_counts
    try:
        union = union_from_reports(
            e0.get("themes") or [], counts, limit=2000, ignore_stop=ignore,
        )
    except RuntimeError as err:
        raise SystemExit(str(err)) from err
    (dest / "union.json").write_text(json.dumps(union), encoding="utf-8")
    ids = union["ids"][: int(n)]
    display_path = _root() / "index" / "display.parquet"
    ext_path = _root() / "index_ext" / "display_ext.parquet"
    metas = {cid: meta_from_files(cid, display_path, ext_path) for cid in ids}
    budget = _budget()
    papers_root = Path(MOUNT) / "papers"
    client = ArxivClient()

    def on_paper(result):
        if over_budget(time.time() - started, 1, budget):
            raise StageBudget(f"{stage} llegó al tope RRM_PASSAGES_BUDGET_USD={budget}")
        return result

    try:
        done = harvest_ids(
            ids,
            metas,
            client=client,
            papers_root=papers_root,
            dest=dest,
            break_lock=os.environ.get("RRM_PASSAGES_BREAK_LOCK") == "1",
            on_paper=on_paper,
        )
    except (ArxivStopped, StageBudget) as err:
        compile_store(dest, quota_source=union.get("quota_source"))
        vol.commit()
        raise SystemExit(f"{stage} se detiene: {err}") from err
    manifest = compile_store(dest, quota_source=union.get("quota_source"))
    vol.commit()
    return _report(stage, started, cpu=1, extra={"n": len(ids), "results": done, "rows": manifest["counts"]})


@app.function(image=gpu_image, gpu="L4", volumes={MOUNT: vol}, secrets=[stage_env], cpu=2, memory=16384, timeout=3600, max_containers=1)
def embed_run(stage: str):
    """Un job corto. Embed de las filas ya parseadas y IndexFlatIP. Luego se apaga."""
    _require(stage)
    from rrm.passages.embed import embed_rows
    from rrm.passages.store import compile_store, load_saved, write_faiss
    from rrm.search.encode import QueryEncoder

    started = time.time()
    dest = _passages()
    _papers, rows, _failures = load_saved(dest)
    if not rows:
        raise SystemExit("no hay filas; la cosecha no escribió papers/")
    encoder = QueryEncoder()
    encoder.load()
    vectors = embed_rows(rows, encoder.encode_proximity, batch=16)
    write_faiss(dest, vectors)
    manifest = compile_store(dest)
    vol.commit()
    return _report(
        stage,
        started,
        cpu=2,
        gpu_l4_seconds=round(time.time() - started, 3),
        extra={"rows": len(rows), "dim": int(vectors.shape[1]) if vectors.ndim == 2 else 0, "index": manifest["index"]},
    )


@app.local_entrypoint()
def e0():
    print(json.dumps(e0_run.remote(), ensure_ascii=False))


@app.local_entrypoint()
def e1():
    print(json.dumps(harvest_run.remote("e1", 5), ensure_ascii=False))


@app.local_entrypoint()
def e2():
    print(json.dumps(harvest_run.remote("e2", 50), ensure_ascii=False))
    print(json.dumps(embed_run.remote("e2"), ensure_ascii=False))


@app.local_entrypoint()
def e3():
    print(json.dumps(harvest_run.remote("e3", 2000), ensure_ascii=False))
    print(json.dumps(embed_run.remote("e3"), ensure_ascii=False))


@app.local_entrypoint()
def e4(symbol: str = r"\sqrt{d_k}", claim: str = "", local: str = ""):
    """E4 vive en el contenedor de búsqueda. Este entrypoint no lo prende."""
    raise SystemExit(
        "E4 consulta BurstSearch, que carga passages/ solo con RRM_PASSAGES=1.\n"
        "RRM_PASSAGES=1 RRM_PASSAGES_STAGE=e4 modal run rrm/search/serve.py::passages_query "
        f"--symbol {json.dumps(symbol)} --claim {json.dumps(claim)} --local {json.dumps(local)}"
    )
