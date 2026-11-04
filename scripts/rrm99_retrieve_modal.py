"""RRM-99: búsqueda de pasajes en Modal (app propia, efímera). Nada pesado en la WSL.

Uso local (crea la app `rrm99-retrieve` sólo mientras dura el `with`):

    from scripts.rrm99_retrieve_modal import remote_search
    hits = remote_search([{"q": "...", "k": 10, "exclude": [cid], "only": None}, ...])

Volumen `rrm-data` montado en /data (sólo lectura de /data/passages). CPU, sin GPU.
No toca `rrm-burst` ni `rrm-reader`.
"""

from __future__ import annotations

import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", extra_index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters", "sentencepiece")
    .run_commands(
        "python -c \"from adapters import AutoAdapterModel; from transformers import AutoTokenizer; "
        "AutoTokenizer.from_pretrained('allenai/specter2_base'); "
        "m = AutoAdapterModel.from_pretrained('allenai/specter2_base'); "
        "m.load_adapter('allenai/specter2_adhoc_query', source='hf', load_as='adhoc_query'); "
        "m.load_adapter('allenai/specter2', source='hf', load_as='proximity')\""
    )
    .add_local_python_source("rrm")
)
app = modal.App("rrm99-retrieve")
vol = modal.Volume.from_name("rrm-data")


@app.cls(image=image, volumes={"/data": vol}, cpu=4, memory=8192, timeout=1800, scaledown_window=120)
class Retriever:
    @modal.enter()
    def load(self):
        import os
        import time

        os.environ["RRM_DATA"] = "/data"
        t = time.time()
        from rrm.reader.analysis import retrieve

        retrieve._load()
        retrieve.encode(["warm up"])
        self.load_s = round(time.time() - t, 1)

    @modal.method()
    def search(self, jobs):
        """jobs: [{q, k, exclude, only, kinds}] → [{hits, ...}] en el mismo orden."""
        import time

        from rrm.reader.analysis import retrieve

        t = time.time()
        out = []
        # Agrupa por (k, exclude, only, kinds) para codificar en lote.
        groups = {}
        for i, job in enumerate(jobs):
            key = (int(job.get("k", 10)), tuple(sorted(job.get("exclude") or [])),
                   None if job.get("only") is None else tuple(sorted(job["only"])), tuple(job.get("kinds") or []))
            groups.setdefault(key, []).append(i)
        res = [None] * len(jobs)
        for (k, excl, only, kinds), idxs in groups.items():
            hits = retrieve.search([jobs[i]["q"] for i in idxs], k=k, exclude=excl, only=only, kinds=list(kinds) or None)
            for i, h in zip(idxs, hits):
                res[i] = h
        return {"results": res, "search_s": round(time.time() - t, 2), "load_s": self.load_s}

    @modal.method()
    def rows(self, pids):
        from rrm.reader.analysis import retrieve

        return [retrieve.row_by_id(p) for p in pids]


def remote_search(jobs):
    with modal.enable_output(), app.run():
        return Retriever().search.remote(jobs)
