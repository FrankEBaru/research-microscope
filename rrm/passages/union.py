"""Unión de temas hasta 2,000 papers únicos, con un cupo por tema."""

import re

LIMIT = 2000
_NOTES = ("survey", "tutorial", "review", "primer")


def title_notes(title):
    """Palabras que se anotan al lado. No mueven el puntaje ni el cupo."""
    words = set(re.findall(r"[a-z0-9]+", (title or "").lower()))
    return [word for word in _NOTES if word in words]


def even_quotas(n_themes, limit=LIMIT):
    """Cupo parejo. La suma es `limit`. El residuo entra desde el primer tema.

    Sirve cuando no hay cuenta de ráfagas en el volumen. Esa cuenta no está
    medida en este código: el origen queda marcado `even` ([I]).
    """
    n_themes = int(n_themes)
    limit = int(limit)
    if n_themes <= 0 or limit <= 0:
        return []
    base, rem = divmod(limit, n_themes)
    return [base + (1 if i < rem else 0) for i in range(n_themes)]


def quotas_for(counts, limit=LIMIT):
    """Proporcional a las ráfagas si todas las cuentas existen. Si no, parejo."""
    counts = list(counts or [])
    if not counts or any(c is None for c in counts) or sum(int(c or 0) for c in counts) <= 0:
        return even_quotas(len(counts), limit), "even"
    total = float(sum(int(c) for c in counts))
    raw = [int(c) / total * int(limit) for c in counts]
    floors = [int(x) for x in raw]
    left = int(limit) - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - floors[i], -i), reverse=True)
    for i in range(max(0, left)):
        floors[order[i]] += 1
    return floors, "bursts"


def union_papers(ranked, quotas, limit=LIMIT):
    """Recorre cada lista ya ordenada y toma papers nuevos hasta llenar su cupo.

    Un paper que ya está en la unión no gasta el cupo del tema siguiente.
    La unión para al llegar a `limit` papers únicos.
    """
    limit = int(limit)
    picked = []
    seen = set()
    took = [0] * len(list(quotas or []))
    themes = list(zip(ranked or [], quotas or []))
    for theme, (ids, quota) in enumerate(themes):
        got = 0
        quota = int(quota)
        for raw in ids or []:
            if len(picked) >= limit or got >= quota:
                break
            cid = int(raw)
            if cid in seen:
                continue
            seen.add(cid)
            picked.append(cid)
            got += 1
        took[theme] = got
        if len(picked) >= limit:
            break
    return picked, took
