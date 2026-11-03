"""Galería estática. No se monta en el lector."""

import json
from pathlib import Path

from rrm.liveart.emulated import CATALOG
from rrm.liveart.offline import gold_widget

FRONT = (
    "positional-encoding",
    "rope-shift",
    "giou-gap",
    "ppo-clip",
    "nerf-freq",
    "vit-patch",
    "attention-scale",
    "stddev",
    "softmax-temperature",
)

_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RRM widgets</title>
<style>
  body { margin: 0; background: #ebe4d6; color: #1c1915; font: 17px/1.45 Palatino, Georgia, serif; }
  header, main { max-width: 820px; margin: 0 auto; padding: 28px 24px; }
  main { padding-top: 0; display: grid; gap: 16px; }
  h1 { font-weight: 500; font-size: 28px; margin: 0 0 8px; }
  header p { margin: 0; color: #5c564c; }
  article { background: #fffdf8; border-radius: 16px; padding: 16px 18px 18px; }
  .eye { margin: 0; font: 12px/1.3 ui-sans-serif, system-ui, sans-serif; letter-spacing: .04em; text-transform: uppercase; color: #8a8175; }
  h2 { font-size: 22px; font-weight: 500; margin: 4px 0 8px; }
  .why { margin: 0 0 12px; color: #3d3832; }
  .row { display: flex; gap: 18px; align-items: flex-start; flex-wrap: wrap; }
  iframe { width: 360px; height: 200px; border: 0; border-radius: 10px; background: #f6f3ec; }
  label { display: grid; gap: 4px; margin: 0 0 10px; font: 13px/1.3 ui-sans-serif, system-ui, sans-serif; color: #5c564c; }
  .err { min-height: 1.2em; color: #8c2f22; font: 13px/1.3 ui-sans-serif, system-ui, sans-serif; }
</style>
</head>
<body>
<header>
  <h1>Widgets de prueba</h1>
  <p>Host aparte del lector. Cada control tiene que mover el parámetro del enunciado.</p>
</header>
<main id="board"></main>
<script id="data" type="application/json">__WIDGETS__</script>
<script>
const widgets = JSON.parse(document.getElementById("data").textContent);
function srcdoc(widget, t0) {
  const state = {w: 360, h: 200};
  for (const knob of widget.controls || []) state[knob.id] = knob.value;
  const safe = String(widget.draw).replace(/<\\/script/gi, "<" + "/script");
  return "<!DOCTYPE html><html><head><meta charset=\\"utf-8\\">" +
    "<meta http-equiv=\\"Content-Security-Policy\\" content=\\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'\\">" +
    "</head><body style=\\"margin:0;background:#f6f3ec;overflow:hidden\\">" +
    "<canvas id=\\"c\\" width=\\"360\\" height=\\"200\\"></canvas><script>" +
    safe +
    "\\n;var ctx=document.getElementById('c').getContext('2d');" +
    "function paint(state,t){draw(ctx,state,t);}" +
    "try{paint(" + JSON.stringify(state) + "," + t0 + ");parent.postMessage({type:'rrm-live',ok:true},'*');}" +
    "catch(e){parent.postMessage({type:'rrm-live',ok:false,error:String(e)},'*');}" +
    "addEventListener('message',function(ev){var m=ev.data||{};if(m.type!=='rrm-params')return;" +
    "try{paint(m.state,m.t||0);}catch(e){parent.postMessage({type:'rrm-frame',ok:false,error:String(e)},'*');}});" +
    "<" + "/script></body></html>";
}

function usesTime(draw) {
  const rest = String(draw).split("\\n").slice(1).join("\\n");
  return /\\bt\\b/.test(rest);
}

function mount(widget) {
  const card = document.createElement("article");
  const q = (widget.questions && widget.questions[0] && widget.questions[0].q) || widget.title;
  card.innerHTML = '<p class="eye"></p><h2></h2><p class="why"></p><div class="row"><div class="stage"></div><div class="controls"></div></div><p class="err"></p>';
  card.querySelector(".eye").textContent = widget.title || widget.id;
  card.querySelector("h2").textContent = q;
  card.querySelector(".why").textContent = widget.explain || "";
  const frame = document.createElement("iframe");
  frame.setAttribute("sandbox", "allow-scripts");
  frame.setAttribute("title", widget.title || widget.id);
  frame.srcdoc = srcdoc(widget, 1.2);
  card.querySelector(".stage").appendChild(frame);
  const err = card.querySelector(".err");
  const values = {};
  for (const knob of widget.controls || []) values[knob.id] = knob.value;
  let t = 1.2;
  let alive = false;
  function state() {
    return Object.assign({w: 360, h: 200}, values);
  }
  function push() {
    if (!frame.contentWindow) return;
    frame.contentWindow.postMessage({type: "rrm-params", state: state(), t: t}, "*");
  }
  frame.addEventListener("load", function () {
    setTimeout(function () { if (!alive) err.textContent = "no arrancó"; }, 800);
  });
  window.addEventListener("message", function (ev) {
    if (ev.source !== frame.contentWindow) return;
    const m = ev.data || {};
    if (m.type === "rrm-live") {
      alive = !!m.ok;
      err.textContent = m.ok ? "" : (m.error || "falló");
      if (m.ok) push();
    } else if (m.type === "rrm-frame" && m.ok === false) {
      err.textContent = m.error || "falló";
    }
  });
  for (const knob of widget.controls || []) {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "range";
    input.min = knob.min;
    input.max = knob.max;
    input.step = knob.step;
    input.value = knob.value;
    const name = document.createElement("span");
    function show() { name.textContent = knob.label + "  " + input.value; }
    input.addEventListener("input", function () {
      values[knob.id] = Number(input.value);
      show();
      push();
    });
    show();
    label.appendChild(name);
    label.appendChild(input);
    card.querySelector(".controls").appendChild(label);
  }
  if (usesTime(widget.draw)) {
    let then = 0;
    function tick(now) {
      if (!then) then = now;
      t += Math.min(0.05, (now - then) / 1000);
      then = now;
      if (alive) push();
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  return card;
}

const board = document.getElementById("board");
const want = (location.hash || "").replace("#", "");
const shown = want ? widgets.filter(function (w) { return w.id === want; }) : widgets;
for (const widget of shown) board.appendChild(mount(widget));
</script>
</body>
</html>
"""


def widgets():
    rows = []
    for name in ("positional_encoding", "softmax_temperature", "attention_scale", "stddev"):
        rows.append(gold_widget(name))
    for row in CATALOG:
        rows.append(row["widget"])
    order = {wid: i for i, wid in enumerate(FRONT)}
    rows.sort(key=lambda item: (order.get(item["id"], len(FRONT)), item["id"]))
    return rows


def html():
    payload = json.dumps(widgets(), ensure_ascii=False).replace("<", "\\u003c")
    return _PAGE.replace("__WIDGETS__", payload)


def write(path=None):
    target = Path(path) if path else Path(__file__).resolve().parents[2] / "liveart" / "host" / "gallery.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html(), encoding="utf-8")
    return target


if __name__ == "__main__":
    print(write())
