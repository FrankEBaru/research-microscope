import test from "node:test";
import assert from "node:assert/strict";
import { atlasModel, lastVisit, nearest, related, suggestOf, trailPairs, yearOffset } from "../src/lib/atlas.js";
import { clusterColor } from "../src/lib/layout.js";

function paper(id, extra = {}) {
  return { corpusid: id, title: `Paper ${id}`, year: 2000 + (id % 7), venue: "Venue", authors: ["Ada Lovelace"], ...extra };
}

test("year offset stays inside a year and does not invent one", () => {
  assert.equal(yearOffset(1), yearOffset(1));
  assert.ok(yearOffset("abc") >= 0 && yearOffset("abc") < 0.9);
  const papers = [paper(1, { year: 1999 }), paper(2, { year: 2010 }), paper(3, { year: null }), paper(4)];
  delete papers[3].year;
  const model = atlasModel({ papers, edges: [], layout: { points: [], groups: [] }, states: {}, explore: null });
  const years = new Set(papers.map((row) => (Number.isInteger(row.year) ? row.year : null)));
  for (const point of model.points) assert.ok(years.has(point.year), `año inventado: ${point.year}`);
  const undated = model.points.find((p) => p.id === "3");
  const also = model.points.find((p) => p.id === "4");
  assert.equal(undated.year, null);
  assert.equal(also.year, null);
  assert.equal(undated.x, model.years.noYearX);
  assert.ok(model.points.find((p) => p.id === "1").x < model.points.find((p) => p.id === "2").x);
  assert.ok(undated.x > model.points.find((p) => p.id === "2").x);
});

test("lanes follow median year, height follows n, one lane has no name", () => {
  const papers = [
    paper(1, { year: 2020 }),
    paper(2, { year: 2022 }),
    paper(3, { year: 2001 }),
    paper(4, { year: 2003 }),
    paper(5, { year: null }),
  ];
  const layout = {
    points: [
      { corpusid: 1, cluster: 1 },
      { corpusid: 2, cluster: 1 },
      { corpusid: 3, cluster: 0 },
      { corpusid: 4, cluster: 0 },
      { corpusid: 5, cluster: 2 },
    ],
    groups: [
      { id: 0, n: 2, name: "early" },
      { id: 1, n: 2, name: "late" },
      { id: 2, n: 1, name: "undated", far: true },
    ],
  };
  const model = atlasModel({ papers, edges: [], layout, states: {}, explore: null });
  assert.deepEqual(model.lanes.map((lane) => lane.id), ["0", "1", "2"]);
  assert.deepEqual(model.lanes.map((lane) => lane.name), ["early", "late", "undated"]);
  assert.deepEqual(model.lanes.map((lane) => lane.color), ["var(--grp-1)", "var(--grp-2)", "var(--grp-3)"]);
  assert.equal(model.lanes[2].far, true);
  assert.ok(model.lanes[0].h > model.lanes[2].h);
  assert.equal(model.lanes[0].far, false);

  const one = atlasModel({
    papers: [paper(1), paper(2)],
    edges: [],
    layout: { points: [], groups: [] },
    states: {},
    explore: null,
  });
  assert.equal(one.lanes.length, 1);
  assert.equal(one.lanes[0].name, "");
  assert.equal(one.points.length, 2);
});

test("parent is the first arrival and a return does not cycle", () => {
  const explore = {
    nodes: [
      { id: "a", at: 1, title: "A" },
      { id: "b", at: 2, title: "B" },
      { id: "c", at: 3, title: "C" },
    ],
    edges: [
      { from: "a", to: "b", at: 2 },
      { from: "b", to: "c", at: 3 },
      { from: "c", to: "b", at: 4 },
      { from: "b", to: "a", at: 5 },
    ],
  };
  const pairs = trailPairs(explore);
  const parent = Object.fromEntries(pairs.map((pair) => [pair.to, pair.from]));
  assert.equal(parent.b, "a");
  assert.equal(parent.c, "b");
  assert.equal(parent.a, undefined);
  assert.equal(lastVisit(explore), "c");
  const seen = new Set();
  for (const id of Object.keys(parent)) {
    const walk = new Set();
    let cur = id;
    while (cur) {
      assert.equal(walk.has(cur), false);
      walk.add(cur);
      cur = parent[cur];
    }
    seen.add(id);
  }
  assert.equal(seen.size, 2);
});

test("related keeps visited papers first and stops at 14", () => {
  const papers = [paper(1, { year: 2010 })];
  const edges = [];
  for (let i = 2; i <= 17; i++) {
    papers.push(paper(i, { year: 2010 + (i % 3) }));
    edges.push({ citing: 1, cited: i });
  }
  const points = papers.map((row, rank) => ({ corpusid: row.corpusid, cluster: 0, rank }));
  const explore = { nodes: [{ id: "17", at: 1, title: "far" }], edges: [] };
  const states = {};
  for (let i = 2; i <= 10; i++) states[String(i)] = { status: "done", source: "latex" };
  const model = atlasModel({
    papers,
    edges,
    layout: { points, groups: [{ id: 0, n: papers.length, name: "all" }] },
    states,
    explore,
  });
  const ids = related(model, "1");
  assert.equal(ids.length, 14);
  assert.equal(ids[0], "17");
  assert.ok(ids.includes("2"));
  assert.equal(related(model, "1", 20).length, 16);
  assert.equal(suggestOf(model), "");
});

test("nearest hits the point under the pointer and misses the rest", () => {
  const model = atlasModel({
    papers: [paper(1, { year: 2000 }), paper(2, { year: 2020 })],
    edges: [],
    layout: { points: [], groups: [] },
    states: {},
    explore: null,
  });
  const point = model.points.find((p) => p.id === "1");
  assert.equal(nearest(model.points, point.x, point.y, 18), "1");
  assert.equal(nearest(model.points, point.x + 40, point.y + 40, 18), null);
  assert.equal(suggestOf(model), "1");
});

test("same-year points stay at least a dot apart", () => {
  const papers = Array.from({ length: 8 }, (_, i) => paper(i + 1, { year: 2018 }));
  const model = atlasModel({ papers, edges: [], layout: { points: [], groups: [] }, states: {}, explore: null });
  for (let a = 0; a < model.points.length; a++) {
    for (let b = a + 1; b < model.points.length; b++) {
      const d = Math.hypot(model.points[a].x - model.points[b].x, model.points[a].y - model.points[b].y);
      assert.ok(d >= 14.5, `${model.points[a].id} and ${model.points[b].id} overlap (${d})`);
    }
  }
});

test("no papers: explore nodes sit on a circle", () => {
  const model = atlasModel({
    papers: [],
    edges: [],
    layout: null,
    states: {},
    explore: { nodes: [{ id: "9", title: "Solo", at: 1 }, { id: "8", title: "Otro", at: 2 }], edges: [{ from: "9", to: "8", at: 2 }] },
  });
  assert.equal(model.lone, true);
  assert.equal(model.points.length, 2);
  assert.equal(model.trail.length, 1);
  assert.equal(model.lanes.length, 0);
});

test("clusterColor is a group token", () => {
  assert.equal(clusterColor(0), "var(--grp-1)");
  assert.equal(clusterColor(5), "var(--grp-6)");
  assert.equal(clusterColor(6), "var(--grp-1)");
  assert.equal(clusterColor("3"), "var(--grp-4)");
  assert.equal(clusterColor(-1), "var(--grp-6)");
});
