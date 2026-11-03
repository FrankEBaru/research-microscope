"""Two real figures for the draw step. Never one generic curve.

The library is the hand-made widgets plus a few catalog neighbors, tagged by
the figure they actually draw. The claim's own id is skipped so a seen topic
is not solved by pasting the answer.
"""

from rrm.liveart.emulated import CATALOG

ARCHETYPES = ("curve", "matrix", "dial", "bars", "blocks", "stream")

# id, archetype. Order is the preference inside an archetype.
LIBRARY = (
    ("adam-valley", "curve"),
    ("pe-sincos", "curve"),
    ("gelu-mix", "curve"),
    ("rms-eps", "curve"),
    ("chinchilla-valley", "curve"),
    ("double-descent", "curve"),
    ("rope-shift", "dial"),
    ("rope-gap", "dial"),
    ("yarn-scale", "dial"),
    ("vit-patch", "matrix"),
    ("giou-gap", "matrix"),
    ("kl-policy", "bars"),
    ("beam-trap", "bars"),
    ("dpo-beta", "bars"),
    ("nucleus-keep", "bars"),
    ("gqa-share", "blocks"),
    ("moe-k", "blocks"),
    ("mqa-share", "blocks"),
    ("paged-blocks", "blocks"),
    ("online-softmax", "stream"),
    ("skip-mix", "stream"),
    ("flow-straight", "stream"),
)

_TOPIC = {
    "adam": "curve",
    "rope": "dial",
    "kl_rlhf": "bars",
    "beam": "bars",
    "dpo_beta": "bars",
    "positional_encoding": "curve",
    "lora": "matrix",
    "gqa": "blocks",
    "moe": "blocks",
    "rmsnorm": "curve",
    "gelu": "curve",
    "chinchilla": "curve",
    "yarn_scale": "dial",
    "vit_patch": "matrix",
    "giou": "matrix",
    "online_softmax": "stream",
    "residual": "stream",
}


def archetype_for(topic):
    return _TOPIC.get(topic or "", "curve")


def shots_for(archetype, topic, claim_id=None, limit=2):
    """Up to two catalog widgets. Two topics. Skip the claim id."""
    if archetype not in ARCHETYPES:
        archetype = "curve"
    by_id = {row["id"]: row for row in CATALOG}
    primary = [
        wid for wid, arch in LIBRARY
        if arch == archetype and wid != claim_id and wid in by_id
    ]

    def topic_of(wid):
        return by_id[wid]["widget"]["topic"]

    first = None
    for wid in primary:
        if topic and topic_of(wid) == topic:
            first = wid
            break
    if first is None and primary:
        first = primary[0]
    second = None
    for wid in primary:
        if wid == first:
            continue
        if first and topic_of(wid) == topic_of(first):
            continue
        second = wid
        break
    if second is None:
        for wid, _arch in LIBRARY:
            if wid == claim_id or wid == first or wid not in by_id:
                continue
            if first and topic_of(wid) == topic_of(first):
                continue
            second = wid
            break
    chosen = [wid for wid in (first, second) if wid][:limit]
    return [_shot(by_id[wid]) for wid in chosen]


def _shot(row):
    widget = row["widget"]
    return {
        "id": widget["id"],
        "topic": widget["topic"],
        "title": widget["title"],
        "explain": widget["explain"],
        "controls": widget["controls"],
        "draw": widget["draw"],
    }
