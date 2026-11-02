// Borrador de la caja. Puro: el componente pone el debounce y elige localStorage.

export function draftKey(paperId, sectionId) {
  const paper = String(paperId ?? "");
  const section = sectionId == null || String(sectionId) === "" ? "_" : String(sectionId);
  return `rrm.draft.v1:${paper}:${section}`;
}

export function legacyKey(paperId) {
  return paperId ? `rrm-ask:${paperId}` : "";
}

export function loadDraft(storage, key) {
  if (!storage || !key) return null;
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const snap = JSON.parse(raw);
    return snap && typeof snap === "object" ? snap : null;
  } catch {
    return null;
  }
}

export function saveDraft(storage, key, snap) {
  if (!storage || !key) return false;
  try {
    storage.setItem(key, JSON.stringify(snap));
    return true;
  } catch {
    return false;
  }
}

/** Secciones con texto no vacío. `_` es la caja sin sectionId. */
export function hasDraft(storage, paperId) {
  const found = new Set();
  if (!storage || paperId == null || String(paperId) === "") return found;
  const prefix = `rrm.draft.v1:${paperId}:`;
  let n = 0;
  try { n = storage.length; } catch { return found; }
  for (let i = 0; i < n; i++) {
    let key = "";
    try { key = storage.key(i) || ""; } catch { continue; }
    if (!key.startsWith(prefix)) continue;
    const snap = loadDraft(storage, key);
    if (!String(snap?.text || "").trim()) continue;
    found.add(key.slice(prefix.length));
  }
  return found;
}

/** Copia `rrm-ask:<id>` a la clave nueva y borra la vieja. No pisa un borrador nuevo. */
export function migrateLegacy(storage, paperId, sectionId) {
  const key = draftKey(paperId, sectionId);
  const current = loadDraft(storage, key);
  if (current) return current;
  const oldKey = legacyKey(paperId);
  const old = loadDraft(storage, oldKey);
  if (!old) return null;
  const snap = {
    text: old.text || "",
    result: old.result ?? null,
    err: old.err || "",
    store: old.store ?? null,
    at: typeof old.at === "number" ? old.at : Date.now(),
  };
  if (saveDraft(storage, key, snap)) {
    try { storage.removeItem(oldKey); } catch { /* la copia nueva ya quedó */ }
  }
  return snap;
}
