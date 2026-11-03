import { PRIMARY } from "./draws.js";
import { VARIANTS } from "./variants.js";
import { VARIANTS2 } from "./variants2.js";
import { VARIANTS3 } from "./variants3.js";
import { EXPLORE, LEADS } from "./explore.js";
import { RICH, RICH_LEADS } from "./rich.js";

export const WIDGETS = [...PRIMARY, ...VARIANTS, ...VARIANTS2, ...VARIANTS3, ...EXPLORE, ...RICH];

// One draw per topic. The first four match the gold ids from RRM-78.
// LEADS cover topics added after the original 14.
export const FEWSHOTS = [...PRIMARY, ...LEADS, ...RICH_LEADS];
export const HIGHLIGHTS = [
  "adam-valley",
  "attn-walk",
  "int8-outlier",
  "rope-shift",
  "beam-trap",
  "denoise-strip",
  "kl-policy",
  "moe-drop",
  "online-softmax",
  "spec-best",
  "chinchilla",
  "pe-sincos",
  "resid-stream",
  "kv-grow",
  "lora-rank",
];
