"""Keeps the explanation step, and rejects a draw the probe would have accepted."""

from __future__ import annotations

import re

_TOY = re.compile(r"juguete|\btoy\b|illustrative|ilustrativ", re.I)
_LIMIT = re.compile(r"solo vale|only holds if|only if|only when", re.I)
_GENERIC = re.compile(r"qu[eé] pasa si|what happens", re.I)
_PREDICT = re.compile(r"^\s*(predice|predict)\b", re.I)
_THRESHOLD = re.compile(r"threshold|umbral", re.I)
_PLATEAU = re.compile(r"plateau|meseta|flatten|se aplana", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_LONG = re.compile(r"\d+\.\d{4,}")
_SPANISH = re.compile(r"[¿¡áéíóúñÁÉÍÓÚÑ]")

# Short pattern taken from the hand-made widgets: a threshold with its value,
# a name = value readout through fmt, and a curve that stops instead of flattening.
PATTERN_DRAW = """\
function draw(ctx, state, t) {
  var top = 36;
  var bot = 286;
  var thr = 2;
  var y = state.lr * 80;
  function fmt(v) { return Math.round(v * 100) / 100; }
  ctx.strokeStyle = "#1f4b99";
  ctx.beginPath();
  ctx.moveTo(48, bot);
  if (y > bot - top) {
    ctx.lineTo(560, top);
    ctx.stroke();
    ctx.fillText("clipped", 500, top + 16);
  } else {
    ctx.lineTo(560, bot - y);
    ctx.stroke();
  }
  var ythr = bot - thr * 16;
  ctx.beginPath();
  ctx.moveTo(48, ythr);
  ctx.lineTo(560, ythr);
  ctx.stroke();
  ctx.fillStyle = "#1f4b99";
  ctx.fillText("threshold " + fmt(thr), 48, ythr - 8);
  ctx.fillText("step = " + fmt(y), 48, 318);
  ctx.fillText("toy", 48, 344);
}
"""


def finish_explain(explain, claim):
    """Keep the explanation step. Append the citation, the toy mark, and the limit if it skipped them."""
    claim = claim or {}
    text = (explain or "").strip()
    arxiv = str(claim.get("arxiv") or "").strip()
    spanish = bool(_SPANISH.search(claim.get("text") or ""))
    extra = []
    if arxiv and arxiv not in text:
        extra.append(f"arXiv {arxiv}.")
    if not _TOY.search(text):
        extra.append("La curva es de juguete, no es una medición." if spanish else "The curve is a toy, not a measurement.")
    if not _LIMIT.search(text):
        extra.append("Solo vale si el control se queda en el rango dibujado." if spanish else "It only holds if the control stays in the drawn range.")
    if extra:
        text = (text + " " + " ".join(extra)).strip()
    if len(text) > 420:
        tail = " ".join(extra) if extra else text[-160:]
        room = 420 - len(tail) - 1
        text = (text[: max(room, 0)].rstrip() + " " + tail).strip()[:420]
    return text


def seal_widget(widget, explain, questions=None):
    """The codegen JSON does not get to replace the explanation step."""
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


def quality_gate(widget, claim):
    """Mechanical rejects the model verifier waved through. Empty means pass."""
    widget = widget or {}
    claim = claim or {}
    draw = widget.get("draw") or ""
    explain = widget.get("explain") or ""
    reasons = []
    if not _THRESHOLD.search(draw):
        reasons.append("no_threshold")
    if "function fmt" not in draw:
        reasons.append("no_fmt")
    if _LONG.search(draw) or _raw_fill(draw):
        reasons.append("raw_decimal")
    arxiv = str(claim.get("arxiv") or "").strip()
    if arxiv and arxiv not in explain:
        reasons.append("no_citation")
    if not _TOY.search(explain):
        reasons.append("no_toy")
    if not _LIMIT.search(explain):
        reasons.append("no_limit")
    reasons.extend(question_problems(widget.get("questions"), widget.get("controls")))
    for control in widget.get("controls") or []:
        if len((control or {}).get("label") or "") > 28:
            reasons.append("label_28")
            break
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


def _first_arg(inside):
    depth = 0
    for i, ch in enumerate(inside):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            return inside[:i]
    return inside


def _fill_args(draw):
    needle = "fillText("
    found, i = [], 0
    while True:
        j = draw.find(needle, i)
        if j < 0:
            break
        k, depth = j + len(needle), 1
        while k < len(draw) and depth:
            if draw[k] == "(":
                depth += 1
            elif draw[k] == ")":
                depth -= 1
            k += 1
        found.append(_first_arg(draw[j + len(needle) : k - 1]))
        i = k
    return found


def _string_only(arg):
    parts = [part.strip() for part in arg.split("+")]
    return bool(parts) and all(re.fullmatch(r'"[^"]*"', part) for part in parts)


def _raw_fill(draw):
    for arg in _fill_args(draw):
        if _string_only(arg):
            continue
        if "fmt(" not in arg:
            return True
    return False


def _contradicts(explain, draw):
    exp, src = explain or "", (draw or "").lower()
    if "clipped" in exp.lower() and "clipped" not in src:
        return True
    if _PLATEAU.search(exp) and "clipped" in src and not _PLATEAU.search(src):
        return True
    return False
