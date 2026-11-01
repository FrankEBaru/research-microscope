import test from "node:test";
import assert from "node:assert/strict";
import { cleanExtract, storeLine } from "../src/lib/extract.js";

test("extractos sin restos de LaTeX", () => {
  assert.equal(cleanExtract("As noted in Table tab:op_complexities, a layer needs $O(n)$ steps."), "As noted in Table, a layer needs $O(n)$ steps.");
  assert.equal(cleanExtract("(Transformer (big) in Table~tab:wmt-results) wins"), "(Transformer (big) in Table) wins");
  assert.equal(cleanExtract("the Penn Treebank [cite], about 40K sentences"), "the Penn Treebank, about 40K sentences");
});

test("almacén honesto: preparando y parado", () => {
  assert.equal(storeLine({ ready: 8, total: 10 }, false), "Preparando frases: 8 de 10 papers…");
  assert.match(storeLine({ ready: 8, total: 10 }, true), /8 de 10 papers\. Los otros 2 no tienen texto/);
  assert.equal(storeLine({ ready: 10, total: 10 }, true), "Frases listas de los 10 papers.");
});

test("RRM-51: una cita que empieza a media frase lleva «…»; NeRF y word2vec no", async () => {
  const { markMidStart } = await import("../src/lib/extract.js");
  assert.equal(markMidStart("based solely on attention"), "…based solely on attention");
  assert.equal(markMidStart("We propose a new architecture."), "We propose a new architecture.");
  assert.equal(markMidStart("mip-NeRF reduces aliasing"), "mip-NeRF reduces aliasing");
  assert.equal(markMidStart("word2vec learns vectors"), "word2vec learns vectors");
  assert.equal(markMidStart("iPhone photos"), "iPhone photos");
  assert.equal(markMidStart("$x$ is small"), "$x$ is small");
});
