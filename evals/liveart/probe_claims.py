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
    {"id": "gae-lambda", "area": "rl", "topic": "gae_lambda", "arxiv": "1506.02438",
     "text": "GAE estimates the advantage with an exponentially weighted sum analogous to TD(lambda). Credit for a reward decays by gamma times lambda at each step backward, and lambda 0 keeps only the one-step term."},
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
    {"id": "lottery-keep", "area": "theory", "topic": "lottery", "arxiv": "1803.03635",
     "text": "The lottery ticket hypothesis says a dense, randomly initialized network contains a winning ticket: a sparse subnetwork that, trained in isolation from its original initialization, reaches test accuracy comparable to the dense network. A random mask of the same size does not."},
    {"id": "beta-vae", "area": "vision", "topic": "beta_vae"},
    {"id": "denoise-ho", "area": "diffusion", "topic": "noise_schedule", "arxiv": "2006.11239",
     "text": "The forward process of a diffusion model has a closed form under a linear noise schedule: beta_t runs from 0.0001 to 0.02 across T=1000 steps, and x_t is sqrt(alpha_bar_t) times x_0 plus sqrt(1 - alpha_bar_t) times epsilon."},
    {"id": "kl-beta", "area": "nlp", "topic": "kl_rlhf", "arxiv": "2203.02155",
     "text": "In RLHF the optimal policy is proportional to the reference policy times exp(reward / beta). A small beta lets the highest-reward token take the whole probability."},
    {"id": "lora-update", "area": "nlp", "topic": "lora", "arxiv": "2106.09685",
     "text": "LoRA freezes the pretrained weights and injects a low-rank update, the product of two matrices of rank r, so a d by d layer trains 2dr values instead of d squared."},
    {"id": "vit-count", "area": "vision", "topic": "vit_patch", "arxiv": "2010.11929",
     "text": "A Vision Transformer splits an image into patches of size P, and the sequence length is the image area divided by P squared. A larger patch size swallows a small object into one token."},
    {"id": "detr-cost", "area": "vision", "topic": "detr_match", "arxiv": "2005.12872",
     "text": "DETR forces unique predictions via bipartite matching between learned object queries and boxes. The matching cost mixes a class term and a box term, so a higher class weight prefers the right label over the nearer box."},
    {"id": "int8-step", "area": "systems", "topic": "", "merit": "skip", "arxiv": "2208.07339",
     "text": "LLM.int8() sets the int8 step by absmax, the row maximum divided by 127, and a feature whose magnitude exceeds 6 stays outside that step."},
    {"id": "erf-gauss", "area": "vision", "topic": "", "merit": "skip", "arxiv": "1701.04128",
     "text": "The effective receptive field of a deep convolutional network is Gaussian and occupies only a fraction of the full theoretical receptive field, which grows with depth and with the kernel."},
    {"id": "gcn-neighbor", "area": "systems", "topic": "", "merit": "skip", "arxiv": "1609.02907",
     "text": "A graph convolutional network mixes each node with its neighbors by a localized first-order filter on the graph, so an isolated node receives no message from that layer."},
    {"id": "clip-cosine", "area": "vision", "topic": "", "merit": "skip", "arxiv": "2103.00020",
     "text": "CLIP learns which caption goes with which image by scoring the cosine of their embeddings divided by a temperature. A lower temperature gives the nearest caption the probability."},
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
    def claim_for(item):
        if item.get("text"):
            return {"text": item["text"], "latex": "", "context": "", "arxiv": item.get("arxiv", "")}
        return by_id[item["id"]]

    out = []
    for item in PROBE_2:
        out.append({**item, "probe": "probe2", "claim": claim_for(item)})
    for item in PROBE_3:
        out.append({**item, "probe": "probe3", "claim": claim_for(item)})
    return out
