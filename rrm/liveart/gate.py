"""Rejects a draw the probe would have waved through.

The check runs the draw. It does not look for a canned sentence in the source.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

_GENERIC = re.compile(r"qu[eé] pasa si|what happens", re.I)
_PREDICT = re.compile(r"^\s*(predice|predict)\b", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_LONG = re.compile(r"\d+\.\d{4,}")
_ARXIV = re.compile(r"\d{4}\.\d{4,5}")
_PLATEAU = re.compile(r"plateau|meseta|flatten|se aplana", re.I)
_THR_WORD = re.compile(r"threshold|umbral", re.I)
_THR_VALUE = re.compile(r"(?:threshold|umbral)\s+(-?\d+(?:\.\d+)?)", re.I)
_THR_VAR = re.compile(r"\bvar\s+thr\s*=\s*(-?\d+(?:\.\d+)?)\s*;")
_THR_FMT = re.compile(r"(?:threshold|umbral)[^\n;]{0,80}fmt\(\s*(-?\d+(?:\.\d+)?)\s*\)", re.I)
_MENTION = re.compile(
    r"\b(?:dragging|moving|raising|lowering|setting)\s+(?:the\s+)?"
    r"([A-Za-z][\w.-]*(?:\s+[A-Za-z][\w.-]*){0,2})",
    re.I,
)
_LEAKS = (
    "name = value",
    "reading name",
    "threshold line stays",
    "with reading",
    "only holds if",
    "solo vale si",
)

_RENDER = Path(__file__).resolve().parents[2] / "apps" / "reader" / "scripts" / "liveart_render.mjs"
_CAP = 200000


def finish_explain(explain, claim):
    """Keep the explanation. Add the arXiv id only when the text skipped it."""
    claim = claim or {}
    text = (explain or "").strip()
    arxiv = str(claim.get("arxiv") or "").strip()
    if arxiv and arxiv not in text:
        extra = f"arXiv {arxiv}."
        room = 420 - len(extra) - 1
        if len(text) > room:
            text = text[: max(room, 0)].rstrip()
        text = (text + " " + extra).strip()
    return text[:420]


def seal_widget(widget, explain, questions=None):
    """The codegen JSON does not get to replace the explanation."""
    out = dict(widget or {})
    if explain:
        out["explain"] = explain
    if questions and not question_problems(questions, out.get("controls")):
        out["questions"] = [dict(item) for item in questions]
    return out


def question_problems(questions, controls):
    if not isinstance(questions, list) or len(questions) != 4:
        return ["generic_questions"]
    texts = []
    for item in questions:
        texts.append((item or {}).get("q") or "" if isinstance(item, dict) else "")
    if any(_GENERIC.search(q) for q in texts) or not any(_PREDICT.search(q) for q in texts):
        return ["generic_questions"]
    for q in texts:
        nums = [float(n) for n in _NUMBER.findall(q)]
        if not nums:
            return ["generic_questions"]
        if controls and not any(_in_range(n, controls) for n in nums):
            return ["generic_questions"]
    return []


def quality_gate(widget, claim, spec=None):
    """Empty means the draw survived the mechanical checks."""
    widget = widget or {}
    claim = claim or {}
    spec = spec if isinstance(spec, dict) else None
    draw = widget.get("draw") or ""
    explain = widget.get("explain") or ""
    controls = widget.get("controls") or []
    reasons = []
    rendered = _render(draw, [_state(controls)])
    base = rendered[0] if rendered else {"error": "render"}
    texts = base.get("texts") or []
    if _leaked(explain) or _leaked(_question_blob(widget)) or _leaked(draw) or any(_leaked(t) for t in texts):
        reasons.append("leaked")
    if _long_in_text("\n".join(texts)):
        reasons.append("raw_decimal")
    arxiv = str(claim.get("arxiv") or "").strip()
    if arxiv and arxiv not in explain:
        reasons.append("no_citation")
    reasons.extend(question_problems(widget.get("questions"), controls))
    if _unknown_question(widget.get("questions"), controls) or _unknown_explain(explain, controls):
        reasons.append("unknown_control")
    for control in controls:
        if len((control or {}).get("label") or "") > 28:
            reasons.append("label_28")
            break
    if _threshold_zero(draw, texts):
        reasons.append("threshold_zero")
    elif _threshold_constant(draw):
        reasons.append("threshold_constant")
    if spec is not None and not str(spec.get("threshold_formula") or "").strip() and (
        _THR_WORD.search(draw) or any(_THR_WORD.search(t or "") for t in texts)
    ):
        reasons.append("threshold_unasked")
    if spec is not None and _wrong_direction(draw, controls, spec):
        reasons.append("direction")
    if _contradicts(explain, draw):
        reasons.append("contradicts")
    return reasons


def _in_range(num, controls):
    for control in controls or []:
        try:
            lo, hi = float(control["min"]), float(control["max"])
        except (KeyError, TypeError, ValueError):
            continue
        if lo - 1e-9 <= num <= hi + 1e-9:
            return True
    return False


def _state(controls, overrides=None):
    state = {"w": 640, "h": 360}
    for control in controls or []:
        if not isinstance(control, dict) or not control.get("id"):
            continue
        try:
            state[control["id"]] = float(control.get("value", control.get("min", 0)))
        except (TypeError, ValueError):
            state[control["id"]] = 0
    if overrides:
        state.update(overrides)
    return state


def _render(draw, states):
    if not draw or not states:
        return [{"error": "empty", "texts": []} for _ in states]
    try:
        proc = subprocess.run(
            ["node", str(_RENDER)],
            input=json.dumps({"draw": draw, "states": states, "cap": _CAP}),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [{"error": str(exc)[:180], "texts": []} for _ in states]
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "render")[:180]
        return [{"error": err, "texts": []} for _ in states]
    try:
        got = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return [{"error": "render-json", "texts": []} for _ in states]
    if not isinstance(got, list) or len(got) != len(states):
        return [{"error": "render-json", "texts": []} for _ in states]
    return got


def _leaked(text):
    low = (text or "").lower()
    return any(phrase in low for phrase in _LEAKS)


def _question_blob(widget):
    parts = []
    for item in widget.get("questions") or []:
        if isinstance(item, dict):
            parts.append(item.get("q") or "")
    return "\n".join(parts)


def _long_in_text(text):
    for match in _LONG.finditer(text or ""):
        if _ARXIV.fullmatch(match.group()):
            continue
        return True
    return False


def _allowed(controls):
    words = set()
    for control in controls or []:
        if not isinstance(control, dict):
            continue
        for blob in (control.get("id") or "", control.get("label") or ""):
            for part in re.split(r"[^A-Za-z0-9]+", str(blob).lower()):
                if part:
                    words.add(part)
    return words


def _mentions(text, controls):
    low = (text or "").lower()
    for control in controls or []:
        if not isinstance(control, dict):
            continue
        cid = str(control.get("id") or "").lower()
        label = str(control.get("label") or "").lower().strip()
        if cid and re.search(rf"\b{re.escape(cid)}\b", low):
            return True
        if label and label in low:
            return True
    return False


def _unknown_question(questions, controls):
    if not controls or not isinstance(questions, list):
        return False
    for item in questions:
        text = (item or {}).get("q") or "" if isinstance(item, dict) else ""
        if text and not _mentions(text, controls):
            return True
    return False


def _unknown_explain(explain, controls):
    allowed = _allowed(controls)
    if not allowed:
        return False
    for match in _MENTION.finditer(explain or ""):
        words = re.findall(r"[A-Za-z0-9]+", match.group(1).lower())
        if words and not any(word in allowed for word in words):
            return True
    return False


def _threshold_zero(draw, texts):
    for match in _THR_VAR.finditer(draw or ""):
        if float(match.group(1)) == 0:
            return True
    for match in _THR_FMT.finditer(draw or ""):
        if float(match.group(1)) == 0:
            return True
    for text in texts or []:
        for match in _THR_VALUE.finditer(text or ""):
            if float(match.group(1)) == 0:
                return True
    return False


def _threshold_constant(draw):
    for match in _THR_VAR.finditer(draw or ""):
        if float(match.group(1)) != 0:
            return True
    for match in _THR_FMT.finditer(draw or ""):
        if float(match.group(1)) != 0:
            return True
    return False


def _readout(texts, name):
    pat = re.compile(rf"(?:^|\s){re.escape(name)}\s*=\s*(-?\d+(?:\.\d+)?)")
    for text in texts or []:
        match = pat.search(text or "")
        if match:
            return float(match.group(1))
    return None


def _wrong_direction(draw, controls, spec):
    """True when a claimed up/down does not show up in the rendered readout."""
    rows = [item for item in (spec.get("direction") or []) if isinstance(item, dict)]
    if not rows:
        return False
    by_id = {c.get("id"): c for c in controls or [] if isinstance(c, dict)}
    jobs = []
    states = []
    for item in rows:
        cid = item.get("control")
        readout = item.get("readout")
        effect = item.get("effect")
        control = by_id.get(cid)
        if effect not in ("up", "down") or not readout or not control:
            return True
        try:
            lo, hi = float(control["min"]), float(control["max"])
        except (KeyError, TypeError, ValueError):
            return True
        if not hi > lo:
            return True
        base = _state(controls)
        low, high = dict(base), dict(base)
        low[cid] = lo
        high[cid] = hi
        jobs.append((len(states), len(states) + 1, str(readout), effect))
        states.extend((low, high))
    rendered = _render(draw, states)
    for lo_i, hi_i, readout, effect in jobs:
        left = rendered[lo_i] if lo_i < len(rendered) else {}
        right = rendered[hi_i] if hi_i < len(rendered) else {}
        if left.get("error") or right.get("error"):
            return True
        a = _readout(left.get("texts"), readout)
        b = _readout(right.get("texts"), readout)
        if a is None or b is None:
            return True
        if effect == "up" and not b > a + 1e-9:
            return True
        if effect == "down" and not b < a - 1e-9:
            return True
    return False


def _contradicts(explain, draw):
    exp, src = explain or "", (draw or "").lower()
    if "clipped" in exp.lower() and "clipped" not in src:
        return True
    if _PLATEAU.search(exp) and "clipped" in src and not _PLATEAU.search(src):
        return True
    return False
