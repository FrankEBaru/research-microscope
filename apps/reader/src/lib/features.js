// RRM_FEATURES on the server, NEXT_PUBLIC_RRM_FEATURES in the browser.
// Default core. "all" is the previous surface (Panorama, compañero, Muse, SAM, instrumento).

export function featuresMode(env = process.env.NEXT_PUBLIC_RRM_FEATURES) {
  return String(env || "core").trim().toLowerCase() === "all" ? "all" : "core";
}

export function coreMode(env) {
  return featuresMode(env) !== "all";
}
