import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";

import { collectV2, compareOf, matrixOf } from "../src/lib/artifacts.js";

const DIR = process.env.RRM_PAPERS_DIR || "/tmp/papers_parsed/papers";

function load(id) {
  return JSON.parse(readFileSync(`${DIR}/${id}.json`, "utf8"));
}

function types(pack) {
  return (pack.artifacts || []).map((item) => item.type);
}

const live = existsSync(DIR);

test("Attention conserva los pies y ResNet cita el supuesto", { skip: !live }, () => {
  const attention = collectV2(load(13756489).rows);
  const scale = attention.artifacts.find((item) => item.type === "con_sin");
  const grid = attention.artifacts.find((item) => item.type === "matriz");
  assert.ok(scale && grid);
  const bars = compareOf(scale.tex);
  assert.equal(bars.legend, "d_k = 64, ilustrativo");
  assert.equal(bars.withLabel, "dividiendo entre √d_k");
  assert.equal(bars.withoutLabel, "sin dividir");
  assert.match(bars.look, /casi todo el peso cae en una sola clave/);
  assert.match(scale.quote || "", /softmax/);
  const heat = matrixOf(grid.tex);
  assert.equal(heat.legend, "d = 64, ilustrativo");
  assert.match(heat.freq, /Cada fila es una dimensión/);
  const resnet = collectV2(load(206594692).rows);
  assert.match(resnet.notes[0].note, /same dimensions/);
  assert.equal(resnet.notes[0].generated, false);
  const rel = collectV2(load(3725815).rows);
  const z = rel.artifacts.find((item) => item.type === "con_sin");
  assert.match(z.scale.withLabel, /d_z/);
});

test("XGBoost parte el algoritmo y el del apéndice de Informer no se muestra", { skip: !live }, () => {
  const boost = collectV2(load(4650265).rows);
  const step = boost.artifacts.find((item) => item.type === "pasos");
  assert.ok(step);
  assert.match(step.title, /Exact Greedy/);
  assert.ok(step.inputs.length >= 1);
  assert.ok(step.steps.length >= 2);
  assert.match(step.steps[2], /to \$m\$ \$G_L/);
  assert.equal(step.steps.some((line) => /\\Do\b|\\EndFor\b|\\[{}]/.test(line)), false);
  const assumed = boost.notes.find((item) => /I_L/.test(item.note));
  assert.equal(assumed.block_id, "4650265:44");
  assert.ok(boost.notes.length <= 3);
  assert.equal(boost.notes.some((item) => item.block_id === "4650265:45"), false);
  const informer = collectV2(load(229156802).rows);
  assert.equal(informer.artifacts.filter((item) => item.type === "pasos").length, 0);
  assert.ok(informer.artifacts.some((item) => item.type === "forma" && /×/.test(item.label)));
  assert.equal(informer.artifacts.some((item) => item.type === "forma" && String(item.block_id).endsWith(":81")), false);
});

test("Boyd tiene a lo más una forma por sección; el inversor muestra ramas", { skip: !live }, () => {
  const boyd = collectV2(load(37925315).rows);
  const by = new Map();
  for (const item of boyd.artifacts.filter((row) => row.type === "forma")) {
    by.set(item.block_id, (by.get(item.block_id) || 0) + 1);
  }
  const sections = new Map();
  for (const row of load(37925315).rows) sections.set(row.id, row.section || "");
  const per = new Map();
  for (const item of boyd.artifacts.filter((row) => row.type === "forma")) {
    const sec = sections.get(item.block_id) || "";
    per.set(sec, (per.get(sec) || 0) + 1);
  }
  assert.ok(per.size > 0);
  assert.ok([...per.values()].every((n) => n === 1));
  assert.ok(boyd.artifacts.filter((row) => row.type === "forma").length <= 3);
  assert.ok(boyd.artifacts.filter((row) => row.type === "pasos").length <= 4);
  const flow = collectV2(load(15216093).rows);
  const branch = flow.artifacts.find((item) => item.type === "casos");
  assert.ok(branch);
  assert.ok(branch.branches.length >= 2);
  assert.match(branch.branches.map((row) => row.cond).join(" "), /leq|otherwise|if/i);
  const traffic = collectV2(load(1085798).rows);
  const flow2 = traffic.artifacts.find((item) => item.type === "casos");
  assert.ok(flow2);
  assert.match(flow2.branches.map((row) => row.cond).join(" "), /if l\(t\)<L/);
  assert.equal(flow2.branches.some((row) => /\\text\{/.test(`${row.expr} ${row.cond}`)), false);
});

test("la DCT dibuja rejilla y Layer Norm no pasa por el softmax", { skip: !live }, () => {
  const dct = collectV2(load(1195959).rows);
  const grid = dct.artifacts.find((item) => item.type === "matriz");
  assert.ok(grid?.grid);
  assert.match(grid.grid.freq, /Cada fila es un k/);
  assert.match(grid.grid.legend, /ilustrativo/);
  const norm = collectV2(load(8236317).rows);
  const drawn = norm.artifacts.find((item) => item.type === "con_sin");
  assert.ok(drawn?.preferScale);
  assert.match(drawn.scale.look, /dividir entre σ/);
  assert.equal(drawn.scale.withLabel.includes("d_k"), false);
});

test("un recorte del paper alcanza para forma, ramas y algoritmo", () => {
  const rows = [
    { id: "h", kind: "h", section: "Modelos", text: "Modelos" },
    { id: "e", kind: "eq", section: "Modelos", latex: String.raw`\mathbf{x}\in \mathbb{R}^{N \times 1}`, text: "" },
    { id: "c", kind: "eq", section: "Modelos", latex: String.raw`\text{Constr}_{j}[q] = \begin{cases} q, & |q| \leq q_j^{max} \\ (q/|q|)q_j^{max}, & \text{otherwise} \end{cases}`, text: "" },
    { id: "a", kind: "p", section: "Algoritmo", text: String.raw`\begin{algorithm} \caption{Exact Greedy Algorithm for Split Finding} \KwIn{$I$, instance set} $gain\leftarrow 0$\\ $G \leftarrow \sum g_i$\\ \end{algorithm}` },
    { id: "s", kind: "p", section: "Algoritmo", text: "assuming that the input and output are of the same dimensions, $\\mathcal{H}(x)-x$." },
  ];
  const pack = collectV2(rows);
  assert.ok(pack.artifacts.some((item) => item.type === "forma" && item.label === "N × 1"));
  assert.ok(pack.artifacts.some((item) => item.type === "casos" && item.branches.length === 2));
  assert.ok(pack.artifacts.some((item) => item.type === "pasos" && /Exact Greedy/.test(item.title)));
  assert.match(pack.notes[0].note, /same dimensions/);
  assert.equal(collectV2(rows, "0").artifacts.length, 0);
});

test("con el flag apagado no sale nada", { skip: !live }, () => {
  const ids = readdirSync(DIR).filter((name) => name.endsWith(".json")).slice(0, 4);
  for (const name of ids) {
    const pack = collectV2(JSON.parse(readFileSync(`${DIR}/${name}`, "utf8")).rows, "0");
    assert.deepEqual(types(pack), []);
    assert.equal(pack.notes.length, 0);
  }
});
