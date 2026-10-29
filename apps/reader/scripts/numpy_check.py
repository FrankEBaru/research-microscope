#!/usr/bin/env python3
"""Reimplementación independiente (numpy) del instrumento √d_k, para comparar con src/lib/instrument.js.
Escribe tests/numpy_reference.json. RNG distinto a propósito: se comparan estadísticas, no muestras."""
import json
import numpy as np

rng = np.random.default_rng(20261029)
out = []
for dk in (16, 64, 256):
    for sigma2 in (1.0, 2.0):
        q = rng.normal(0, np.sqrt(sigma2), size=(20000, dk))
        k = rng.normal(0, np.sqrt(sigma2), size=(20000, dk))
        dots = (q * k).sum(axis=1)
        out.append({"dk": dk, "sigma2": sigma2, "var": float(dots.var(ddof=1)),
                    "scaledVar": float((dots / np.sqrt(dk)).var(ddof=1)), "mean": float(dots.mean())})
json.dump(out, open("tests/numpy_reference.json", "w"), indent=1)
print(f"numpy {np.__version__}: {len(out)} configuraciones")
