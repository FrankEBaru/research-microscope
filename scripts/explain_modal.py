"""RRM-100: la evaluación de Explain corre en Modal, no en la WSL (9 GB).

    modal run scripts/explain_modal.py --cmd "--cands E1,E2 --tag r2"

App propia `rrm-exp-100` (efímera con `modal run`: se apaga al terminar).
`rrm-data` se monta en solo lectura; la caché de Meta, el gold y los resultados
viven en el volumen `rrm-exp-100` (/exp). Nunca despliega rrm-reader ni rrm-burst.
"""

import os
import shlex
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", extra_index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters")
    .run_commands(
        "python -c \"from transformers import AutoTokenizer; from adapters import AutoAdapterModel; "
        "AutoTokenizer.from_pretrained('allenai/specter2_base'); "
        "m = AutoAdapterModel.from_pretrained('allenai/specter2_base'); "
        "m.load_adapter('allenai/specter2_adhoc_query', source='hf', load_as='adhoc_query', set_active=True); "
        "m.load_adapter('allenai/specter2', source='hf', load_as='proximity')\"",
    )
    .add_local_python_source("rrm")
    .add_local_file(str(ROOT / "scripts" / "explain_eval.py"), "/opt/explain_eval.py")
)
app = modal.App("rrm-exp-100")
data = modal.Volume.from_name("rrm-data").read_only()
exp = modal.Volume.from_name("rrm-exp-100", create_if_missing=True)
secret = modal.Secret.from_dict({"MODEL_API_KEY": os.environ.get("MODEL_API_KEY", "")}) if modal.is_local() else modal.Secret.from_dict({})


@app.function(image=image, volumes={"/data": data, "/exp": exp}, secrets=[secret], cpu=4, memory=6144, timeout=3600)
def run_eval(cmd: str) -> str:
    import subprocess
    import sys

    os.environ["RRM_EXPLAIN_CACHE"] = "/exp/cache"
    Path("/exp/runs").mkdir(parents=True, exist_ok=True)
    argv = shlex.split(cmd)
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else "run"
    full = [sys.executable, "/opt/explain_eval.py", "--gold", "/exp/gold.json", "--papers", "/data/papers",
            "--passages", "/data/passages", "--out", f"/exp/runs/{tag}.json", *argv]
    proc = subprocess.run(full, capture_output=True, text=True, cwd="/root")
    log = "\n".join(line for line in proc.stderr.splitlines() if line.startswith(("E", "WARN", "passages", "Trace", "  File", "Error")) or "Error" in line)
    Path(f"/exp/runs/{tag}.log").write_text(proc.stderr, encoding="utf-8")
    exp.commit()
    return log + "\n" + proc.stdout


@app.function(image=image, volumes={"/data": data, "/exp": exp}, secrets=[secret], cpu=4, memory=6144, timeout=3600)
def traces(sections: str = "") -> str:
    """Respuestas reales de /ask (motor final) para cada respuesta del gold, en el formato de rrm/offline.py:
    /exp/traces/ask/index.json con filas {focus, text, stage, file} y un JSON por respuesta.
    Las hojas y vectores quedan en /exp/traces/store (RRM_EXPLAIN_DIR)."""
    import json
    import time

    os.environ["RRM_EXPLAIN_DIR"] = "/exp/traces/store"
    os.environ["RRM_EXPLAIN_CACHE"] = "/exp/cache"  # mismas llamadas que la ronda 3: no se pagan dos veces
    from rrm.reader.explain import service
    from rrm.reader.explain.retrieve import passage_base
    from rrm.reader.pipeline import load_paper
    from rrm.reader.similar import specter_encode

    gold = json.loads(Path("/exp/gold.json").read_text(encoding="utf-8"))
    out_dir = Path("/exp/traces/ask")
    out_dir.mkdir(parents=True, exist_ok=True)
    only = {x for x in sections.split(",") if x}
    base = passage_base("/data/passages")
    index, log, spent = [], [], 0.0
    for sec in gold["sections"]:
        key = f"{sec['paper']}:{sec['section']}"
        if only and key not in only:
            continue
        folder = Path("/data/papers") / str(sec["paper"])
        paper = load_paper(folder)
        t0 = time.perf_counter()
        prep = service.prepare(folder, paper, encode=specter_encode, base=base, sections=[sec["section"]])
        spent += prep["cost"]["cost_usd"]
        log.append(f"prep {key} {prep['seconds']}s ${prep['cost']['cost_usd']:.5f}")
        for ai, ans in enumerate(sec["answers"]):
            text = " ".join(c["text"] for c in ans["claims"])
            for stage in ("frases", "revisar"):
                t1 = time.perf_counter()
                body = service.ask(folder, paper, sec["section"], text, stage=stage, encode=specter_encode)
                name = f"{sec['paper']}-{sec['section']}-{ai}-{ans['kind']}-{stage}.json"
                (out_dir / name).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
                index.append({"focus": str(sec["paper"]), "section": sec["section"], "text": text, "stage": stage, "file": name})
                spent += (body.get("meta") or {}).get("cost_usd", 0.0) if isinstance(body.get("meta"), dict) else 0.0
                log.append(f"{name} {body.get('engine')} {time.perf_counter() - t1:.1f}s")
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    exp.commit()
    return "\n".join(log) + f"\nTOTAL ${spent:.5f}"


@app.local_entrypoint()
def main(cmd: str = "--cands E1 --tag smoke", trace: str = ""):
    if trace:
        print(traces.remote("" if trace == "all" else trace))
    else:
        print(run_eval.remote(cmd))
