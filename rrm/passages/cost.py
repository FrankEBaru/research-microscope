"""Tarifas copiadas de rrm/reader/serve.py (modal.com/pricing, 2026-10-28).

Sirven para un estimado [I]. No incluyen la memoria. No son un costo medido:
`measured` queda en false hasta que una etapa corra y anote sus segundos.
"""

CPU_USD_PER_CORE_S = 0.0000131
L4_USD_PER_S = 0.000222

# Plan de máquina, no una corrida. Segundos y GPU son [I].
STAGE_PLAN = {
    "e0": {
        "seconds": 3600,
        "cpu": 4,
        "gpu_l4_seconds": 0,
        "why": "k-means en muestra, asignar 8.8 M en CPU, puntaje y sonda; sin e-prints",
    },
    "e1": {
        "seconds": 120,
        "cpu": 1,
        "gpu_l4_seconds": 0,
        "why": "5 papers: e-print a ≥8 s, licencia apagada, parseo en CPU",
    },
    "e2": {
        "seconds": 400,
        "cpu": 1,
        "gpu_l4_seconds": 120,
        "why": "50 papers en CPU y un embed corto en L4",
    },
    "e3": {
        "seconds": 18000,
        "cpu": 1,
        "gpu_l4_seconds": 900,
        "why": "2,000 papers por capas a ≥8 s, licencia apagada, parseo y embed en L4",
    },
    "e4": {
        "seconds": 180,
        "cpu": 2,
        "gpu_l4_seconds": 0,
        "why": "arrancar BurstSearch, una consulta, apagar",
    },
}


def estimate_usd(*, seconds, cpu=0, gpu_l4_seconds=0):
    cpu_usd = float(seconds) * float(cpu) * CPU_USD_PER_CORE_S
    gpu_usd = float(gpu_l4_seconds) * L4_USD_PER_S
    return {
        "usd_cpu": cpu_usd,
        "usd_gpu_l4": gpu_usd,
        "usd_total": cpu_usd + gpu_usd,
        "measured": False,
        "note": "[I] tarifas de rrm/reader/serve.py (2026-10-28). No incluye memoria.",
    }


def stage_estimate(stage):
    plan = STAGE_PLAN[stage]
    out = estimate_usd(
        seconds=plan["seconds"],
        cpu=plan["cpu"],
        gpu_l4_seconds=plan["gpu_l4_seconds"],
    )
    out["stage"] = stage
    out["why"] = plan["why"]
    out["seconds"] = plan["seconds"]
    return out


def over_budget(elapsed_s, cpu, budget_usd):
    """True si el estimado de CPU ya llegó al tope. None no tiene tope."""
    if budget_usd is None or budget_usd == "":
        return False
    est = estimate_usd(seconds=float(elapsed_s), cpu=float(cpu))
    return est["usd_total"] >= float(budget_usd)
