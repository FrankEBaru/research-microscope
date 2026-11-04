"""Rejects a draw the probe would have waved through.

The check runs the draw. It does not look for a canned sentence in the source.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

from rrm.liveart.contract import CANVAS_METHODS, CANVAS_PROPS, HOST, VERSION_04, normalize_04

_PREDICT = re.compile(r"^\s*(predice|predict)\b", re.I)
_SET = re.compile(r"\b(?:set|pon|mueve)\b", re.I)
_HAPPENS = re.compile(r"what happens|qu[eé] pasa", re.I)
_WATCH_PHRASE = re.compile(r"\s+(?:and|y)\s+(?:watch|mira|look)\s+", re.I)
_MISREAD = re.compile(r"\b(?:expect|predice|predict|think|cree|suppose|malentend|wrong)\b", re.I)
_ES = re.compile(
    r"[áéíóúñ¿¡]|\b(?:el|la|los|las|que|para|por|una|del|este|esta|comparten|comparte|bloques|bloque)\b",
    re.I,
)
_EN = re.compile(r"\b(?:the|and|with|when|what|watch|from|this|that|queries|heads)\b", re.I)
_SIGNED = re.compile(r"-?\d+(?:\.\d+)?")
_JUNK_LABEL = re.compile(r"\b(?:holds|pow)\b", re.I)
# Phrases the round-4 prompt leaked into explain. Not a ban on "bounded by sqrt(v)".
_FILLER = (
    "condition of the topic",
    "condición del tema",
    "condicion del tema",
    "valley condition",
    "the bound is",
    "bounded by absolute positions",
    "bounded by the valley condition",
)
_KV_IDS = {"kv_heads", "kvheads", "kv_head", "n_kv"}
_Q_IDS = {"q_heads", "qheads", "q_head", "query_heads", "n_q"}
_CLIPPED = re.compile(r"\bclipped\b", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_LONG = re.compile(r"\d+\.\d{4,}")
_ARXIV = re.compile(r"\d{4}\.\d{4,5}")
_PLATEAU = re.compile(r"plateau|meseta|flatten|se aplana", re.I)
_THR_WORD = re.compile(r"threshold|umbral", re.I)
_THR_VALUE = re.compile(r"(?:threshold|umbral)\s+(-?\d+(?:\.\d+)?)", re.I)
_THR_VAR = re.compile(r"\bvar\s+thr\s*=\s*(-?\d+(?:\.\d+)?)\s*;")
_THR_FMT = re.compile(r"(?:threshold|umbral)[^\n;]{0,80}fmt\(\s*(-?\d+(?:\.\d+)?)\s*\)", re.I)
_KINDS = {"sign", "level", "cross2", "knee", "endpoint"}
_CHAR_W = 7
_ASCENT = 12
_DESCENT = 3
_PURE_NUM = re.compile(r"-?\d+(?:\.\d+)?")
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
_VERIFY = Path(__file__).resolve().parents[2] / "apps" / "reader" / "scripts" / "liveart_verify.mjs"
_ALLOWED_CTX = set(CANVAS_METHODS)
_ALLOWED_PROP = set(CANVAS_PROPS)
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


def _fix_question(text):
    """End on '?', and use 'Set X to v: what happens to Y?'."""
    raw = str(text or "").strip()
    spanish = bool(re.search(r"[áéíóúñ¿¡]|\bpon\b", raw, re.I)) and not re.search(r"\bset\b", raw, re.I)
    repl = ": qué pasa con " if spanish else ": what happens to "
    raw = _WATCH_PHRASE.sub(repl, raw, count=1)
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = re.sub(r"[.\s]+$", "", raw)
    if raw and not raw.endswith("?"):
        raw += "?"
    return raw


def _skip_string(src, i):
    quote = src[i]
    i += 1
    n = len(src)
    while i < n:
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == quote:
            return i + 1
        i += 1
    return n


def _hoist_functions(draw):
    """The engine does not hoist. A function used above its declaration is undeclared."""
    spans = []
    n = len(draw)
    i = 0
    depth = 0
    while i < n:
        c = draw[i]
        if c in "\"'":
            i = _skip_string(draw, i)
            continue
        if c == "{":
            depth += 1
            i += 1
            continue
        if c == "}":
            depth -= 1
            i += 1
            continue
        if depth == 1 and draw.startswith("function ", i):
            start = i
            j = draw.find("{", i)
            if j < 0:
                break
            d = 0
            k = j
            end = None
            while k < n:
                if draw[k] in "\"'":
                    k = _skip_string(draw, k)
                    continue
                if draw[k] == "{":
                    d += 1
                elif draw[k] == "}":
                    d -= 1
                    if d == 0:
                        end = k + 1
                        break
                k += 1
            if end is None:
                break
            spans.append((start, end))
            i = end
            depth = 1
            continue
        i += 1
    if not spans:
        return draw
    chunks = [draw[a:b].strip() for a, b in spans]
    out = draw
    for a, b in reversed(spans):
        out = out[:a] + out[b:]
    first = out.find("{")
    if first < 0:
        return draw
    return out[: first + 1] + "\n" + "\n".join(chunks) + "\n" + out[first + 1 :]


def _strip_calls(draw):
    """Drop ctx calls the engine rejects. setLineDash is the one Spark keeps writing."""

    def repl(match):
        if match.group(1) in _ALLOWED_CTX:
            return match.group(0)
        return ""

    draw = re.sub(r"ctx\.([A-Za-z]+)\s*\([^;]*\)\s*;?", repl, draw)

    def bare(match):
        name = match.group(1)
        if name in _ALLOWED_CTX or name in _ALLOWED_PROP:
            return match.group(0)
        return ""

    return re.sub(r"ctx\.([A-Za-z]+)\s*;", bare, draw)


def sanitize_widget(widget):
    """Deterministic pass before verifyWidget. No model call."""
    out = dict(widget or {})
    v04 = out.get("version") == VERSION_04
    if v04:
        out = normalize_04(out)
    questions = []
    for item in out.get("questions") or []:
        if not isinstance(item, dict):
            questions.append(item)
            continue
        fixed = dict(item)
        fixed["q"] = _fix_question(item.get("q") or "")
        questions.append(fixed)
    if questions:
        out["questions"] = questions
    draw = out.get("draw") or ""
    if draw:
        out["draw"] = _strip_calls(_hoist_functions(draw))
        if v04:
            # R1: the 0.4 draw writes no text; readouts and takeaway carry it.
            out["draw"] = re.sub(r"ctx\.fillText\s*\([^;]*\)\s*;?", "", out["draw"])
    return out


def question_problems(questions, controls, regime=None):
    """Four questions, each 'Set X to v: what happens to Y?'.

    One states the misconception, one sits on a regime value, two read a number.
    """
    if not isinstance(questions, list) or len(questions) != 4:
        return ["generic_questions"]
    texts = []
    for item in questions:
        texts.append((item or {}).get("q") or "" if isinstance(item, dict) else "")
    if not all(_SET.search(q) and _HAPPENS.search(q) for q in texts):
        return ["generic_questions"]
    if sum(1 for q in texts if _MISREAD.search(q)) != 1:
        return ["generic_questions"]
    for q in texts:
        nums = [float(n) for n in _NUMBER.findall(q)]
        if not nums:
            return ["generic_questions"]
        if controls and not any(_in_range(n, controls) for n in nums):
            return ["generic_questions"]
        if controls and not any(_names(q, control) for control in controls if isinstance(control, dict)):
            return ["generic_questions"]
    if regime and not _one_regime_question(texts, controls, regime):
        return ["generic_questions"]
    return []


def quality_gate(widget, claim, spec=None):
    """Empty means the draw survived the mechanical checks."""
    _WIDGET_04["widget"] = widget if isinstance(widget, dict) and widget.get("version") == VERSION_04 else None
    try:
        return _quality_gate(widget, claim, spec)
    finally:
        _WIDGET_04["widget"] = None


def _quality_gate(widget, claim, spec=None):
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
    if _filler(explain):
        reasons.append("filler")
    regime = spec.get("regime") if spec is not None else None
    reasons.extend(question_problems(widget.get("questions"), controls, regime))
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
    if spec is not None and _constraint_broken(controls, spec.get("constraints")):
        reasons.append("constraint")
    if _heads_dont_divide(controls):
        reasons.append("divides")
    if _few_stops(controls):
        reasons.append("steps")
    if _mixed_language(widget, claim, texts):
        reasons.append("language")
    if spec is not None and _scale_problem(spec, texts):
        reasons.append("scale")
    if spec is not None and _regime_problem(draw, controls, spec.get("regime"), base, spec):
        reasons.append("regime")
    if spec is not None and _margin_problem(controls, spec.get("regime")):
        reasons.append("margin")
    if _default_hides(controls, widget.get("questions")):
        reasons.append("default")
    if _readability(base.get("glyphs") or [], spec.get("scale") if spec is not None else None):
        reasons.append("readability")
    # 0.4: a legend in the host names the series, so a bar needs no word beside it in the canvas.
    if _unexplained_shapes(base) and not (widget.get("version") == VERSION_04 and widget.get("legend")):
        reasons.append("shapes")
    if _dead_label(draw, controls):
        reasons.append("dead_label")
    if _contradicts(explain, draw):
        reasons.append("contradicts")
    for reason in _engine_reasons(widget, claim):
        if reason not in reasons:
            reasons.append(reason)
    return reasons


def _predicts_control(question, controls):
    """Predict/Predice, plus a control id or label, plus a number in that range."""
    if not _PREDICT.search(question or ""):
        return False
    nums = [float(n) for n in _SIGNED.findall(question or "")]
    if not nums:
        return False
    if not controls:
        return True
    for control in controls:
        if not isinstance(control, dict) or not _names(question, control):
            continue
        try:
            lo, hi = float(control["min"]), float(control["max"])
        except (KeyError, TypeError, ValueError):
            continue
        if any(lo - 1e-9 <= n <= hi + 1e-9 for n in nums):
            return True
    return False


def _names(question, control):
    cid = str(control.get("id") or "")
    label = str(control.get("label") or "").strip()
    if cid and re.search(rf"\b{re.escape(cid)}\b", question or "", re.I):
        return True
    if label and re.search(rf"\b{re.escape(label)}\b", question or "", re.I):
        return True
    return False


def _filler(explain):
    text = (explain or "").lower()
    return any(phrase in text for phrase in _FILLER)


def _one_regime_question(texts, controls, regime):
    """At least one question lands on a regime value, or the nearest stop."""
    targets = []
    state = _state(controls)
    for item in regime or []:
        if not isinstance(item, dict):
            continue
        try:
            value = float(_expr_value(str(item.get("formula") or ""), state))
        except (ValueError, KeyError, ZeroDivisionError, TypeError):
            continue
        tol = 0.06
        cid = item.get("control")
        for control in controls or []:
            if isinstance(control, dict) and control.get("id") == cid:
                try:
                    tol = max(0.06, float(control.get("step") or 0) / 2)
                except (TypeError, ValueError):
                    tol = 0.06
                break
        targets.append((value, tol))
    if not targets:
        return True
    hits = 0
    for text in texts:
        signed = [float(n) for n in _SIGNED.findall(text or "")]
        if any(abs(num - value) <= tol for num in signed for value, tol in targets):
            hits += 1
    return hits >= 1


def _few_stops(controls):
    """A slider with fewer than 4 reachable values is a collapsed range."""
    for control in controls or []:
        if not isinstance(control, dict):
            continue
        # #64 kinds: a toggle, select, button, pick or predict is discrete on purpose.
        if (control.get("kind") or "slider") not in ("slider", "drag"):
            continue
        try:
            lo = float(control["min"])
            hi = float(control["max"])
            step = float(control.get("step") or 0)
        except (KeyError, TypeError, ValueError):
            return True
        if step <= 0 or hi < lo:
            return True
        if int(round((hi - lo) / step)) + 1 < 4:
            return True
    return False


def _mixed_language(widget, claim, texts=None):
    """Title, labels, questions, explain and canvas text stay in the claim's language."""
    parts = [
        widget.get("title") or "",
        widget.get("explain") or "",
    ]
    for control in widget.get("controls") or []:
        if isinstance(control, dict):
            parts.append(control.get("label") or "")
    parts.append(_question_blob(widget))
    parts.extend(texts or [])
    blob = "\n".join(parts)
    claim_text = (claim or {}).get("text") or ""
    if _ES.search(claim_text):
        return bool(_EN.search(blob))
    return bool(_ES.search(blob))


def _scale_problem(spec, texts):
    """'not to scale' only when the figure is a schematic, not a real axis."""
    blob = "\n".join(texts or []).lower()
    phrase = "not to scale" in blob
    scale = spec.get("scale")
    if scale is False and not phrase:
        return True
    if scale is True and phrase:
        return True
    if phrase and re.search(r"\baxis\b", blob):
        return True
    return False


def regime_out_of_range(spec):
    """True when a formula falls outside its slider, or a non-endpoint sits under 2 steps from an end.

    Missing or empty regime is not this: codegen still runs.
    """
    if not isinstance(spec, dict):
        return False
    regime = spec.get("regime")
    if not isinstance(regime, list) or not regime:
        return False
    controls = spec.get("controls") or []
    try:
        state = _state(controls)
    except (KeyError, TypeError, ValueError):
        return False
    by_id = {c.get("id"): c for c in controls if isinstance(c, dict)}
    for item in regime:
        if not isinstance(item, dict):
            return False
        control = by_id.get(item.get("control"))
        if control is None:
            return False
        try:
            value = float(_expr_value(str(item.get("formula") or ""), state))
            lo = float(control["min"])
            hi = float(control["max"])
        except (KeyError, TypeError, ValueError):
            return False
        if value < lo - 1e-6 or value > hi + 1e-6 or _short_margin(item, control, value):
            return True
    return False


def _short_margin(item, control, value):
    """A non-endpoint needs two steps of slider on each side. An endpoint is the end."""
    if str((item or {}).get("kind") or "") == "endpoint":
        return False
    try:
        step = float(control.get("step") or 0)
        lo = float(control["min"])
        hi = float(control["max"])
    except (KeyError, TypeError, ValueError):
        return False
    if step <= 0:
        return False
    return (value - lo) < 2 * step - 1e-6 or (hi - value) < 2 * step - 1e-6


def _regime_problem(draw, controls, regime, rendered, spec):
    """The mark is labeled. sign, level, cross2 and knee use that item's readout. endpoint is the mark only."""
    del spec
    if not isinstance(regime, list) or not regime:
        return True
    state = _state(controls)
    by_id = {c.get("id"): c for c in controls or [] if isinstance(c, dict)}
    glyphs = rendered.get("glyphs") or []
    for item in regime:
        if not isinstance(item, dict):
            return True
        label = str(item.get("label") or "").strip()
        cid = str(item.get("control") or "")
        control = by_id.get(cid)
        if not label or control is None:
            return True
        try:
            value = float(_expr_value(str(item.get("formula") or ""), state))
            lo = float(control["min"])
            hi = float(control["max"])
            step = float(control.get("step") or 0)
        except (KeyError, TypeError, ValueError):
            return True
        if step <= 0 or value < lo - 1e-6 or value > hi + 1e-6:
            return True
        nearest = round((value - lo) / step) * step + lo
        if abs(nearest - value) > step / 2 + 1e-6:
            return True
        if not _label_on_mark(glyphs, rendered, label, value):
            return True
        if not _regime_kind_ok(draw, controls, item, value, lo, hi, step, glyphs):
            return True
    return False


def _regime_kind_ok(draw, controls, item, value, lo, hi, step, glyphs):
    kind = str(item.get("kind") or "")
    if kind == "endpoint":
        return True
    if kind not in _KINDS:
        return False
    names = [part.strip() for part in str(item.get("readout") or "").split(",") if part.strip()]
    if not names or (kind == "cross2" and len(names) < 2):
        return False
    if kind == "knee":
        return _knee_ok(draw, controls, names[0], str(item.get("control") or ""), value, lo, hi, step)
    left = min(max(lo, value - step), hi)
    right = max(min(hi, value + step), lo)
    if right - left < step * 0.5:
        return False
    samples = _samples(draw, controls, str(item.get("control") or ""), [left, value, right], names)
    if samples is None:
        return False
    if kind == "sign":
        return _sign_ok(samples[0])
    if kind == "level":
        return _level_ok(item, glyphs, value, samples[0])
    if kind == "cross2":
        return _cross2_ok(samples[0], samples[1])
    return False


def _samples(draw, controls, cid, points, names):
    states = []
    for point in points:
        state = _state(controls)
        state[cid] = point
        states.append(state)
    rendered = _render(draw, states)
    if len(rendered) != len(points) or any(row.get("error") for row in rendered):
        return None
    return [[_readout(row.get("texts"), name) for row in rendered] for name in names]


def _sign_ok(samples):
    vals = [v for v in samples if v is not None]
    if len(vals) < 2:
        return False
    if any(a * b < 0 for i, a in enumerate(vals) for b in vals[i + 1 :]):
        return True
    return any(v == 0 for v in vals) and any(v != 0 for v in vals)


def _level_ok(item, glyphs, value, samples):
    """The readout crosses a number in the label, or meets it when the mark is the end of the slider."""
    label = str(item.get("label") or "")
    nums = [float(n) for n in _SIGNED.findall(label)]
    low = label.lower()
    for glyph in glyphs or []:
        text = str(glyph.get("t") or "")
        if low and low in text.lower():
            nums.extend(float(n) for n in _SIGNED.findall(text))
    if not nums or any(v is None for v in samples):
        return False
    others = [n for n in nums if abs(n - value) > 0.05]
    level = others[0] if others else nums[0]
    vals = list(samples)
    if any((a - level) * (b - level) < 0 for i, a in enumerate(vals) for b in vals[i + 1 :]):
        return True
    near = any(abs(v - level) <= 0.05 for v in vals)
    far = any(abs(v - level) > 0.05 for v in vals)
    return near and far


def _cross2_ok(left, right):
    diffs = []
    for a, b in zip(left, right):
        if a is None or b is None:
            return False
        diffs.append(a - b)
    for i, d1 in enumerate(diffs):
        for d2 in diffs[i + 1 :]:
            if d1 * d2 < 0 or (abs(d1) <= 1e-9) != (abs(d2) <= 1e-9):
                return True
    return False


def _knee_ok(draw, controls, name, cid, value, lo, hi, step):
    """Slopes on the two sides differ. Widen until fmt (2 decimals) can show it."""
    delta = step if step > 0 else max(hi - lo, 1e-6) / 8
    best = None
    for _ in range(6):
        left = max(lo, value - delta)
        right = min(hi, value + delta)
        samples = _samples(draw, controls, cid, [left, value, right], [name])
        if samples is None or any(v is None for v in samples[0]):
            return False
        best = (left, value, right, samples[0])
        vals = samples[0]
        if len({round(v, 2) for v in vals}) > 1 and right - left > step * 0.5:
            break
        nxt = delta * 4
        if left <= lo + 1e-9 and right >= hi - 1e-9:
            break
        delta = nxt
    left, mid, right, (a, m, b) = best
    dx1, dx2 = mid - left, right - mid
    if dx1 <= 1e-9 or dx2 <= 1e-9:
        return False
    s1, s2 = (m - a) / dx1, (b - m) / dx2
    if s1 * s2 < 0:
        return True
    big, small = max(abs(s1), abs(s2)), min(abs(s1), abs(s2))
    if small <= 1e-12:
        return big > 1e-12
    return big / small >= 1.25


def _margin_problem(controls, regime):
    if not isinstance(regime, list) or not regime:
        return False
    state = _state(controls)
    by_id = {c.get("id"): c for c in controls or [] if isinstance(c, dict)}
    for item in regime:
        if not isinstance(item, dict):
            continue
        control = by_id.get(item.get("control"))
        if control is None:
            continue
        try:
            value = float(_expr_value(str(item.get("formula") or ""), state))
        except (ValueError, KeyError, ZeroDivisionError, TypeError):
            continue
        if _short_margin(item, control, value):
            return True
    return False


def _default_hides(controls, questions):
    """The misconception is already on screen: that question's number is the control's value."""
    texts = []
    for item in questions or []:
        texts.append((item or {}).get("q") or "" if isinstance(item, dict) else "")
    mis = [q for q in texts if _MISREAD.search(q)]
    if len(mis) != 1:
        return False
    nums = [float(n) for n in _SIGNED.findall(mis[0])]
    named = False
    for control in controls or []:
        if not isinstance(control, dict) or not _names(mis[0], control):
            continue
        named = True
        try:
            value = float(control.get("value"))
            step = float(control.get("step") or 0)
        except (TypeError, ValueError):
            return True
        if any(abs(n - value) <= max(0.06, step / 2) for n in nums):
            return False
    return named


def _readability(glyphs, scale):
    """No text outside the canvas, no overlapping boxes, and two tick numbers on each data axis."""
    if _text_off(glyphs) or _text_overlap(glyphs):
        return True
    if scale is True and not _two_axis_numbers(glyphs):
        return True
    return False


def _glyph_box(glyph):
    text = str(glyph.get("t") or "")
    x = float(glyph.get("x") or 0)
    y = float(glyph.get("y") or 0)
    return x, y - _ASCENT, x + max(len(text), 1) * _CHAR_W, y + _DESCENT


def _text_off(glyphs):
    width, height = HOST["canvas_w"], HOST["canvas_h"]
    for glyph in glyphs or []:
        if not str(glyph.get("t") or ""):
            continue
        left, top, right, bottom = _glyph_box(glyph)
        if left < -1 or top < -1 or right > width + 1 or bottom > height + 1:
            return True
    return False


def _text_overlap(glyphs):
    boxes = [_glyph_box(g) for g in glyphs or [] if str(g.get("t") or "")]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            iw = min(a[2], b[2]) - max(a[0], b[0])
            ih = min(a[3], b[3]) - max(a[1], b[1])
            if iw > 4 and ih > 4:
                return True
    return False


def _two_axis_numbers(glyphs):
    pts = []
    for glyph in glyphs or []:
        if _PURE_NUM.fullmatch(str(glyph.get("t") or "").strip()):
            pts.append((float(glyph.get("x") or 0), float(glyph.get("y") or 0)))

    def axis(index, other):
        groups = []
        for point in pts:
            for group in groups:
                if abs(point[index] - group[0][index]) <= 10:
                    group.append(point)
                    break
            else:
                groups.append([point])
        for group in groups:
            coords = [point[other] for point in group]
            if len(group) >= 2 and max(coords) - min(coords) > 24:
                return True
        return False

    return axis(1, 0) and axis(0, 1)


def _engine_reasons(widget, claim):
    """#59 verifyWidget. reasons plus detail (ctx:setLineDash, undeclared:fmt) go to repair."""
    if not widget or not widget.get("draw"):
        return []
    claim_text = ""
    if isinstance(claim, dict):
        claim_text = claim.get("text") or ""
    elif claim:
        claim_text = str(claim)
    try:
        proc = subprocess.run(
            ["node", str(_VERIFY)],
            input=json.dumps({"widget": widget, "claim": claim_text}),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ["engine"]
    if proc.returncode != 0:
        return ["engine"]
    try:
        got = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return ["engine"]
    if got.get("accept"):
        return []
    out = []
    for item in (got.get("reasons") or []) + (got.get("detail") or []):
        if item and item not in out:
            out.append(item)
    return out


def _label_on_mark(glyphs, rendered, label, value):
    want = label.lower()
    for glyph in glyphs:
        text = str(glyph.get("t") or "")
        if want not in text.lower():
            continue
        nums = [float(n) for n in _SIGNED.findall(text)]
        if not any(abs(num - value) <= 0.05 for num in nums):
            continue
        if _near_geometry(glyph, rendered):
            return True
    return False


def _near_geometry(glyph, rendered, pad=48):
    x = float(glyph.get("x") or 0)
    y = float(glyph.get("y") or 0)
    for seg in rendered.get("segs") or []:
        if _dist_seg(x, y, seg) <= pad:
            return True
    for rect in rendered.get("rects") or []:
        if _near_rect(x, y, rect, pad):
            return True
    return False


def _dist_seg(x, y, seg):
    x0, y0 = float(seg.get("x0") or 0), float(seg.get("y0") or 0)
    x1, y1 = float(seg.get("x1") or 0), float(seg.get("y1") or 0)
    dx, dy = x1 - x0, y1 - y0
    length = dx * dx + dy * dy
    if length <= 1e-9:
        return math.hypot(x - x0, y - y0)
    t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / length))
    return math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))


def _near_rect(x, y, rect, pad):
    left = float(rect.get("x") or 0)
    top = float(rect.get("y") or 0)
    right = left + float(rect.get("w") or 0)
    bottom = top + float(rect.get("h") or 0)
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top
    return (left - pad) <= x <= (right + pad) and (top - pad) <= y <= (bottom + pad)


def _unexplained_shapes(rendered):
    """A filled block with no word beside it."""
    rects = []
    for rect in rendered.get("rects") or []:
        w = abs(float(rect.get("w") or 0))
        h = abs(float(rect.get("h") or 0))
        if w >= 480 and h >= 200:
            continue
        if w * h < 36:
            continue
        rects.append(rect)
    if not rects:
        return False
    glyphs = [g for g in (rendered.get("glyphs") or []) if _caption(g.get("t"))]
    groups = _shape_groups(rects)
    for group in groups:
        if not any(
            _near_rect(float(g.get("x") or 0), float(g.get("y") or 0), rect, 150)
            for g in glyphs
            for rect in group
        ):
            return True
    return False


def _caption(text):
    """A nearby word that names the shape, not a name = number readout."""
    raw = str(text or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_ ]+=\s*-?\d+(?:\.\d+)?", raw):
        return False
    return any(len(word) >= 4 for word in re.findall(r"[A-Za-z]+", raw))


def _shape_groups(rects):
    parent = list(range(len(rects)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, left in enumerate(rects):
        for j in range(i + 1, len(rects)):
            if _rects_touch(left, rects[j], 24):
                join(i, j)
    buckets = {}
    for i in range(len(rects)):
        buckets.setdefault(find(i), []).append(rects[i])
    return list(buckets.values())


def _rects_touch(a, b, gap):
    ax, ay = float(a.get("x") or 0), float(a.get("y") or 0)
    aw, ah = abs(float(a.get("w") or 0)), abs(float(a.get("h") or 0))
    bx, by = float(b.get("x") or 0), float(b.get("y") or 0)
    bw, bh = abs(float(b.get("w") or 0)), abs(float(b.get("h") or 0))
    return not (ax + aw + gap < bx or bx + bw + gap < ax or ay + ah + gap < by or by + bh + gap < ay)


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


# 0.4 (RRM-90): quality_gate sets the widget so every _render of its draw gets the ui helpers.
# Off unless the widget says rrm-widget/0.4 and RRM_LIVEART_V04 is on (the node script checks both).
_WIDGET_04 = {"widget": None}


def _render(draw, states):
    if not draw or not states:
        return [{"error": "empty", "texts": []} for _ in states]
    job = {"draw": draw, "states": states, "cap": _CAP}
    current = _WIDGET_04["widget"]
    if isinstance(current, dict) and current.get("draw") == draw:
        job["widget"] = current
    try:
        proc = subprocess.run(
            ["node", str(_RENDER)],
            input=json.dumps(job),
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
    """Last number on a text that names the readout.

    Accepts `name v`, `name = v`, and `name = expr = v`.
    """
    if not name:
        return None
    pat = re.compile(rf"(?:^|\s){re.escape(str(name))}\b.*?(-?\d+(?:\.\d+)?)\s*$")
    for text in texts or []:
        match = pat.search(text or "")
        if match:
            return float(match.group(1))
    return None


def _dead_label(draw, controls):
    """A label that never changes, or that the state does not support."""
    base = _state(controls)
    states = [base]
    for control in controls or []:
        if not isinstance(control, dict) or not control.get("id"):
            continue
        try:
            lo, hi = float(control["min"]), float(control["max"])
        except (KeyError, TypeError, ValueError):
            continue
        low, high = dict(base), dict(base)
        low[control["id"]] = lo
        high[control["id"]] = hi
        states.extend((low, high))
    rendered = _render(draw, states)
    # 0.4: host lines (readouts, takeaway, control marks) are not canvas labels.
    for item in rendered:
        host = item.get("host")
        if host:
            item["texts"] = [t for t in item.get("texts") or [] if t not in host]
    blobs = []
    for item in rendered:
        if item.get("error"):
            continue
        blobs.append("\n".join(item.get("texts") or []))
    if not blobs:
        return False
    if any(_JUNK_LABEL.search(blob) for blob in blobs):
        return True
    if all(_CLIPPED.search(blob) for blob in blobs):
        return True
    paired = []
    for state, item in zip(states, rendered):
        if item.get("error"):
            continue
        paired.append((state, "\n".join(item.get("texts") or [])))
    return _fixed_control_text(paired, controls)


def _fixed_control_text(paired, controls):
    """`m = 7` painted as text while the slider is not 7."""
    ids = []
    for control in controls or []:
        cid = str((control or {}).get("id") or "")
        if cid:
            ids.append(cid)
    for state, blob in paired:
        for cid in ids:
            for shown in _fixed_numbers(blob, cid):
                try:
                    actual = float(state.get(cid))
                except (TypeError, ValueError):
                    return True
                if abs(shown - actual) > 0.01:
                    return True
    return False


def _fixed_numbers(blob, cid):
    """Numbers in `id = number` where id is the whole left side.

    `m = 7 shifts` counts. `m x f = 2` does not: f is the last factor, not the label.
    """
    pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(cid)}\s*=\s*(-?\d+(?:\.\d+)?)")
    found = []
    for match in pat.finditer(blob or ""):
        j = match.start() - 1
        while j >= 0 and blob[j] in " \t":
            j -= 1
        # A previous fillText ends at the newline. It is not part of this label.
        if j >= 0 and blob[j] != "\n" and (blob[j].isalnum() or blob[j] in "._)*+/xX-\u2212"):
            continue
        found.append(float(match.group(1)))
    return found


def _heads_dont_divide(controls):
    """Every reachable kv stop has to divide every reachable query-head stop."""
    kv = q = None
    for control in controls or []:
        if not isinstance(control, dict):
            continue
        cid = str(control.get("id") or "").lower()
        if cid in _KV_IDS:
            kv = control
        elif cid in _Q_IDS:
            q = control
    if kv is None or q is None:
        return False
    kv_stops, q_stops = _stops(kv), _stops(q)
    if not kv_stops or not q_stops:
        return True
    if len(kv_stops) * len(q_stops) > 400:
        kv_stops, q_stops = _thin(kv_stops, 20), _thin(q_stops, 20)
    for kv_v in kv_stops:
        for q_v in q_stops:
            if kv_v <= 1e-9:
                return True
            ratio = q_v / kv_v
            if abs(ratio - round(ratio)) > 1e-6:
                return True
    return False


def _stops(control, cap=48):
    try:
        lo = float(control["min"])
        hi = float(control["max"])
        step = float(control.get("step") or 0)
    except (KeyError, TypeError, ValueError):
        return []
    if step <= 0 or hi < lo:
        return []
    count = int(round((hi - lo) / step)) + 1
    if count < 1:
        return []
    if count <= cap:
        return [lo + i * step for i in range(count)]
    stride = max(1, (count - 1) // (cap - 1))
    idxs = list(range(0, count, stride))
    if idxs[-1] != count - 1:
        idxs.append(count - 1)
    return [lo + i * step for i in idxs]


def _thin(stops, cap):
    if len(stops) <= cap:
        return stops
    stride = max(1, (len(stops) - 1) // (cap - 1))
    picked = stops[::stride]
    if picked[-1] != stops[-1]:
        picked.append(stops[-1])
    return picked


def _constraint_broken(controls, constraints):
    """True when some slider corner breaks a declared comparison."""
    checks = []
    for item in constraints or []:
        text = item if isinstance(item, str) else ""
        text = text.replace("≤", "<=").replace("≥", ">=").replace("−", "-").strip()
        if text:
            checks.append(text)
    if not checks:
        return False
    for state in _corners(controls):
        for text in checks:
            if not _holds(text, state):
                return True
    return False


def _corners(controls):
    states = [{}]
    for control in controls or []:
        if not isinstance(control, dict) or not control.get("id"):
            continue
        try:
            lo, hi = float(control["min"]), float(control["max"])
        except (KeyError, TypeError, ValueError):
            return []
        nxt = []
        for state in states:
            low = dict(state)
            low[control["id"]] = lo
            nxt.append(low)
            if hi != lo:
                high = dict(state)
                high[control["id"]] = hi
                nxt.append(high)
        states = nxt
    return states or [{}]


def _holds(text, state):
    try:
        tokens = _lex(text)
        pos = 0

        def peek():
            return tokens[pos] if pos < len(tokens) else None

        def take():
            nonlocal pos
            tok = tokens[pos]
            pos += 1
            return tok

        def parse_expr():
            node = parse_term()
            while peek() in ("+", "-"):
                op = take()
                right = parse_term()
                node = (op, node, right)
            return node

        def parse_term():
            node = parse_unary()
            while peek() in ("*", "/"):
                op = take()
                right = parse_unary()
                node = (op, node, right)
            return node

        def parse_unary():
            if peek() == "-":
                take()
                return ("neg", parse_unary())
            return parse_primary()

        def parse_primary():
            tok = peek()
            if tok is None:
                raise ValueError("end")
            if isinstance(tok, tuple) and tok[0] == "num":
                take()
                return ("num", tok[1])
            if isinstance(tok, tuple) and tok[0] == "id":
                take()
                if peek() == "(" and tok[1] in ("abs", "sqrt"):
                    take()
                    inner = parse_expr()
                    if take() != ")":
                        raise ValueError(")")
                    return (tok[1], inner)
                return ("var", tok[1])
            if tok == "(":
                take()
                inner = parse_expr()
                if take() != ")":
                    raise ValueError(")")
                return inner
            raise ValueError("primary")

        left = parse_expr()
        op = peek()
        if op not in ("<=", ">=", "<", ">"):
            return False
        take()
        right = parse_expr()
        if pos != len(tokens):
            return False
        a, b = _value(left, state), _value(right, state)
    except (ValueError, KeyError, ZeroDivisionError, TypeError):
        return False
    if op == "<=":
        return a <= b + 1e-9
    if op == ">=":
        return a + 1e-9 >= b
    if op == "<":
        return a < b - 1e-9
    return a > b + 1e-9


def _lex(text):
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text.startswith("<=", i) or text.startswith(">=", i):
            out.append(text[i : i + 2])
            i += 2
            continue
        if ch in "+-*/()<>":
            out.append(ch)
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            j = i + 1
            while j < len(text) and (text[j].isdigit() or text[j] == "."):
                j += 1
            out.append(("num", float(text[i:j])))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            out.append(("id", text[i:j]))
            i = j
            continue
        raise ValueError(ch)
    return out


def _value(node, state):
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        if node[1] not in state:
            raise KeyError(node[1])
        return float(state[node[1]])
    if kind == "neg":
        return -_value(node[1], state)
    if kind == "abs":
        return abs(_value(node[1], state))
    if kind == "sqrt":
        inner = _value(node[1], state)
        if inner < 0:
            raise ValueError("sqrt")
        return inner ** 0.5
    if kind == "ln":
        inner = _value(node[1], state)
        if inner <= 0:
            raise ValueError("ln")
        return math.log(inner)
    if kind == "pi":
        return math.pi
    left, right = _value(node[1], state), _value(node[2], state)
    if kind == "+":
        return left + right
    if kind == "-":
        return left - right
    if kind == "*":
        return left * right
    if right == 0:
        raise ZeroDivisionError
    return left / right


def _expr_value(text, state):
    """Value of a regime formula. Same operators as a constraint side, plus ln and pi."""
    tokens = _lex((text or "").replace("−", "-").strip())
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        return tok

    def parse_expr():
        node = parse_term()
        while peek() in ("+", "-"):
            op = take()
            node = (op, node, parse_term())
        return node

    def parse_term():
        node = parse_unary()
        while peek() in ("*", "/"):
            op = take()
            node = (op, node, parse_unary())
        return node

    def parse_unary():
        if peek() == "-":
            take()
            return ("neg", parse_unary())
        return parse_primary()

    def parse_primary():
        tok = peek()
        if tok is None:
            raise ValueError("end")
        if isinstance(tok, tuple) and tok[0] == "num":
            take()
            return ("num", tok[1])
        if isinstance(tok, tuple) and tok[0] == "id":
            take()
            if peek() == "(" and tok[1] in ("abs", "sqrt", "ln"):
                take()
                inner = parse_expr()
                if take() != ")":
                    raise ValueError(")")
                return (tok[1], inner)
            if tok[1] == "pi":
                return ("pi",)
            return ("var", tok[1])
        if tok == "(":
            take()
            inner = parse_expr()
            if take() != ")":
                raise ValueError(")")
            return inner
        raise ValueError("primary")

    node = parse_expr()
    if pos != len(tokens):
        raise ValueError("tail")
    return _value(node, state)


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
