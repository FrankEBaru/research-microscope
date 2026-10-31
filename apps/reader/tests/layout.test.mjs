import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { layoutOf, mapCaption, placePapers, statusLine } from "../src/lib/layout.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));

function serverLayout(papers, edges) {
  const py = spawnSync("python3", ["-c", `
import json, sys
from rrm.search.layout import place_papers
raw = json.load(sys.stdin)
print(json.dumps(place_papers(raw["papers"], raw["edges"])))
`], { input: JSON.stringify({ papers, edges }), encoding: "utf8", cwd: root });
  assert.equal(py.status, 0, py.stderr);
  return JSON.parse(py.stdout);
}

test("el layout del navegador coincide con el del servidor", () => {
  const papers = [
    { corpusid: 1, year: 1990, title: "A" },
    { corpusid: 2, year: 2010, title: "B" },
    { corpusid: 3, title: "C" },
  ];
  const edges = [{ citing: 2, cited: 1 }, { citing: 9, cited: 1 }];
  const py = serverLayout(papers, edges);
  const js = placePapers(papers, edges);
  assert.equal(js.method, "year-citation");
  assert.deepEqual(js.links, py.links);
  assert.equal(js.links.length, 1);
  js.points.forEach((point, i) => {
    assert.ok(Math.abs(point.x - py.points[i].x) < 0.02, `${point.x} vs ${py.points[i].x}`);
    assert.ok(Math.abs(point.y - py.points[i].y) < 0.02, `${point.y} vs ${py.points[i].y}`);
  });
  assert.ok(js.points[0].x < js.points[1].x);
  assert.ok(js.points[1].x < js.points[2].x);
});

test("un layout SPECTER2 del servidor no se reemplaza por el círculo", () => {
  const papers = [{ corpusid: 1, title: "A" }, { corpusid: 2, title: "B" }];
  const layout = {
    method: "specter2-pca",
    points: [
      { corpusid: 1, x: 10, y: 20, cluster: 0, rank: 0 },
      { corpusid: 2, x: 30, y: 40, cluster: 1, rank: 1 },
    ],
    variance: [0.4, 0.2],
    cosine_min: 0.8,
    groups: [{ id: 0, n: 1 }, { id: 1, n: 1 }],
    similarity: [{ a: 1, b: 2, cosine: 0.9 }],
  };
  const got = layoutOf({ papers, edges: [], layout });
  assert.equal(got.method, "specter2-pca");
  assert.equal(got.points[0].x, 10);
  const caption = mapCaption(got);
  assert.match(caption.position, /PCA de SPECTER2 \(60% de la varianza\)/);
  assert.match(caption.positionTitle, /SPECTER2/);
});

test("sin citas el rótulo no dice que sea SPECTER2", () => {
  const layout = placePapers([{ corpusid: 1, year: 2000 }, { corpusid: 2, year: 2020 }], []);
  assert.equal(layout.method, "rank-circle");
  const caption = mapCaption(layout);
  assert.match(caption.positionTitle, /no una similitud/i);
  assert.doesNotMatch(caption.position, /SPECTER/);
});

test("la línea de estado no bloquea y cuenta las fases", () => {
  const papers = [{ corpusid: 1 }, { corpusid: 2 }, { corpusid: 3 }];
  const line = statusLine(papers, { 1: { status: "queued" }, 2: { status: "done" }, 3: { status: "failed" } });
  assert.equal(line, "1 preparando · 1 listo · 1 falló");
  assert.equal(statusLine([{ corpusid: 4 }, { corpusid: 5 }], {}), "2 encontrados");
});
