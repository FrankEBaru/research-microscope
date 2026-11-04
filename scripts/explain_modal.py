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


@app.local_entrypoint()
def main(cmd: str = "--cands E1 --tag smoke"):
    print(run_eval.remote(cmd))
