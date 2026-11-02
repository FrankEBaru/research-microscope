import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");
const raw = {};
for (const m of css.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) raw[m[1]] = m[2].trim();

function hex(name, seen = []) {
  let v = raw[name];
  assert.ok(v, `falta ${name}`);
  const ref = v.match(/^var\((--[\w-]+)\)$/);
  if (ref) return hex(ref[1]);
  const h = v.match(/^#([0-9a-f]{6})$/i);
  assert.ok(h, `${name} no es #rrggbb: ${v}`);
  return [0, 2, 4].map((i) => parseInt(h[1].slice(i, i + 2), 16));
}
function lum([r, g, b]) {
  const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function ratio(a, b) {
  const [x, y] = [lum(hex(a)), lum(hex(b))].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

test("texto y acento sobre page y page-2 >= 4.5", () => {
  for (const fg of ["--ink", "--ink-2", "--ink-3", "--accent", "--accent-h", "--prov-generated"])
    for (const bg of ["--page", "--page-2"])
      assert.ok(ratio(fg, bg) >= 4.5, `${fg} sobre ${bg}: ${ratio(fg, bg).toFixed(2)}`);
});

test("accent-ink sobre accent >= 4.5", () => {
  assert.ok(ratio("--accent-ink", "--accent") >= 4.5);
});

test("grupos y datos sobre page >= 3", () => {
  for (const fg of ["--grp-1", "--grp-2", "--grp-3", "--grp-4", "--grp-5", "--grp-6", "--data-raw"])
    assert.ok(ratio(fg, "--page") >= 3, `${fg}: ${ratio(fg, "--page").toFixed(2)}`);
});
