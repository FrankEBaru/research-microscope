"""Rejects a draw the probe would have waved through.

The check runs the draw. It does not look for a canned sentence in the source.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

_PREDICT = re.compile(r"^\s*(predice|predict)\b", re.I)
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
    """Exactly four questions, and one of them predicts a named control.

    The question may say "Predict what happens". It has to name a real control
    and a number inside that control's range. No other veto.
    """
    if not isinstance(questions, list) or len(questions) != 4:
        return ["generic_questions"]
    texts = []
    for item in questions:
        texts.append((item or {}).get("q") or "" if isinstance(item, dict) else "")
    if not any(_predicts_control(q, controls) for q in texts):
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
    if _filler(explain):
        reasons.append("filler")
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
    if spec is not None and _constraint_broken(controls, spec.get("constraints")):
        reasons.append("constraint")
    if _heads_dont_divide(controls):
        reasons.append("divides")
    if spec is not None and spec.get("scale") is False and "not to scale" not in "\n".join(texts).lower():
        reasons.append("scale")
    if _dead_label(draw, controls):
        reasons.append("dead_label")
    if _contradicts(explain, draw):
        reasons.append("contradicts")
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
        if j >= 0 and blob[j] != "\n" and (blob[j].isalnum() or blob[j] in "._)*+/xX"):
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
