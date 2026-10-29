#!/usr/bin/env node
"use strict";
/* Batch KaTeX check. stdin: JSON array of TeX strings. stdout: JSON array of booleans.
   Tries the string, then equation and align wrappers, so align bodies still count. */
const katex = require("katex");
const fs = require("fs");

const items = JSON.parse(fs.readFileSync(0, "utf8") || "[]");
const out = items.map((tex) => {
  const tries = [tex, "\\begin{equation}" + tex + "\\end{equation}", "\\begin{align}" + tex + "\\end{align}"];
  for (const t of tries) {
    try {
      katex.renderToString(t, { throwOnError: true, displayMode: true });
      return true;
    } catch (e) {
      /* next wrap */
    }
  }
  return false;
});
process.stdout.write(JSON.stringify(out));
