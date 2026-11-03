import { PRIMARY } from "./draws.js";
import { VARIANTS } from "./variants.js";
import { VARIANTS2 } from "./variants2.js";
import { VARIANTS3 } from "./variants3.js";
import { EXPLORE, LEADS } from "./explore.js";

export const WIDGETS = [...PRIMARY, ...VARIANTS, ...VARIANTS2, ...VARIANTS3, ...EXPLORE];

// One draw per topic. The first four match the gold ids from RRM-78.
// LEADS cover topics added in the explore pass.
export const FEWSHOTS = [...PRIMARY, ...LEADS];
export const HIGHLIGHTS = [
  "pe-sincos",
  "rope-shift",
  "adam-valley",
  "lora-rank",
  "kl-policy",
  "beam-trap",
  "bn-stable",
  "chinchilla",
  "spec-best",
  "online-softmax",
  "tau-near",
];
