"""Listas para las sondas reales. Cada id ya es un widget del banco offline.

Sonda 2: los fallos de la sonda 1 (syntax, idioma, bucles, selector) y un
primer corte de otras áreas. Sonda 3: el resto del mapa, sin repetir ids.
"""

PROBE_2 = (
    {"id": "ppo", "area": "rl", "topic": "ppo_clip"},
    {"id": "nerf", "area": "vision", "topic": "nerf_freq"},
    {"id": "yarn-parts", "area": "nlp", "topic": "yarn_parts"},
    {"id": "beam", "area": "nlp", "topic": "beam"},
    {"id": "bpe", "area": "nlp", "topic": "bpe_merge"},
    {"id": "nucleus", "area": "nlp", "topic": "nucleus"},
    {"id": "gqa", "area": "nlp", "topic": "gqa"},
    {"id": "alibi", "area": "nlp", "topic": "alibi"},
    {"id": "dropout", "area": "nlp", "topic": "dropout"},
    {"id": "warmup", "area": "optimization", "topic": "warmup"},
    {"id": "rope", "area": "nlp", "topic": "rope"},
    {"id": "swiglu", "area": "nlp", "topic": "swiglu"},
    {"id": "speculative", "area": "nlp", "topic": "speculative"},
    {"id": "ddim-eta", "area": "diffusion", "topic": "ddim_eta"},
    {"id": "double-descent", "area": "theory", "topic": "double_descent"},
    {"id": "paged-blocks", "area": "systems", "topic": "paged_attn"},
    {"id": "grok-delay", "area": "theory", "topic": "grokking"},
    {"id": "decision-rtg", "area": "rl", "topic": "decision_rtg"},
    {"id": "cutmix-area", "area": "vision", "topic": "cutmix"},
    {"id": "flow-straight", "area": "diffusion", "topic": "flow_match"},
)

PROBE_3 = (
    {"id": "mixup-lambda", "area": "vision", "topic": "mixup"},
    {"id": "mae-ratio", "area": "vision", "topic": "mae_mask"},
    {"id": "arcface-margin", "area": "vision", "topic": "arcface"},
    {"id": "gae-lambda", "area": "rl", "topic": "gae_lambda"},
    {"id": "sac-alpha", "area": "rl", "topic": "sac_temp"},
    {"id": "eps-greedy", "area": "rl", "topic": "eps_greedy"},
    {"id": "consistency-steps", "area": "diffusion", "topic": "consistency_model"},
    {"id": "minsnr-gamma", "area": "diffusion", "topic": "min_snr"},
    {"id": "cosine-mix", "area": "diffusion", "topic": "cosine_snr"},
    {"id": "adamw-decay", "area": "optimization", "topic": "adamw"},
    {"id": "sam-rho", "area": "optimization", "topic": "sam_rho"},
    {"id": "batch-lr", "area": "optimization", "topic": "batch_scale"},
    {"id": "zero-stage", "area": "systems", "topic": "zero_stage"},
    {"id": "gpipe-bubble", "area": "systems", "topic": "pipe_bubble"},
    {"id": "ckpt-segments", "area": "systems", "topic": "grad_ckpt"},
    {"id": "ia3-scale", "area": "nlp", "topic": "ia3_scale"},
    {"id": "performer-m", "area": "nlp", "topic": "performer_m"},
    {"id": "rwkv-decay", "area": "nlp", "topic": "rwkv_time"},
    {"id": "deepnorm-alpha", "area": "nlp", "topic": "deepnorm"},
    {"id": "lottery-keep", "area": "theory", "topic": "lottery"},
    {"id": "beta-vae", "area": "vision", "topic": "beta_vae"},
)


def claims():
    """Une el banco con el id de cada fila. El texto es el del caso, no una copia."""
    from evals.liveart.cases import selector_cases
    from rrm.liveart.wave2 import SPECS

    by_id = {}
    for row in selector_cases():
        by_id[row["id"]] = row["claim"]
    for spec in SPECS:
        by_id[spec["id"]] = {
            "text": spec["claim"],
            "latex": "",
            "context": "",
            "arxiv": spec["arxiv"],
        }
    out = []
    for probe, item in (("probe2", row) for row in PROBE_2):
        out.append({**item, "probe": probe, "claim": by_id[item["id"]]})
    for item in PROBE_3:
        out.append({**item, "probe": "probe3", "claim": by_id[item["id"]]})
    return out
