import test from "node:test";
import assert from "node:assert/strict";

import { splitRich } from "../src/lib/richtext.js";

test("la fórmula sin $ se separa y $d_k$ no se toca aquí", () => {
  const parts = splitRich("antes \\mathrm{FFN}(x)=\\max(0, xW_1 + b_1) W_2 + b_2 While the linear");
  assert.equal(parts.find((p) => p[0] === "d")[1], "\\mathrm{FFN}(x)=\\max(0, xW_1 + b_1) W_2 + b_2");
  assert.match(parts.filter((p) => p[0] === "t").map((p) => p[1]).join(""), /While the linear/);
  assert.deepEqual(splitRich("el símbolo $d_k$ y $d_v$"), [["t", "el símbolo $d_k$ y $d_v$"]]);
});
