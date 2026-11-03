import { PRIMARY } from "./draws.js";
import { VARIANTS } from "./variants.js";
import { VARIANTS2 } from "./variants2.js";
import { VARIANTS3 } from "./variants3.js";

export const WIDGETS = [...PRIMARY, ...VARIANTS, ...VARIANTS2, ...VARIANTS3];

// One draw per topic. The first four match the gold ids from RRM-78.
export const FEWSHOTS = PRIMARY;
