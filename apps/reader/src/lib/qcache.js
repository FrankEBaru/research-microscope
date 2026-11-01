// Last K questions in the browser. The key matches rrm/search/qcache.py.

export const QUESTION_CACHE_LIMIT = 10;
const STORAGE_KEY = "rrm.questions.v1";

export function normalizeQuestion(text) {
  return String(text || "").trim().replace(/\s+/g, " ").toLowerCase();
}

export function readQuestions(storage) {
  if (!storage) return [];
  try {
    const raw = storage.getItem(STORAGE_KEY);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export function recallQuestion(storage, question) {
  const key = normalizeQuestion(question);
  if (!key) return null;
  return readQuestions(storage).find((row) => row && row.q === key) || null;
}

export function rememberQuestion(storage, question, payload, overflow) {
  const key = normalizeQuestion(question);
  if (!key || !storage) return [];
  const row = { q: key, payload, at: Date.now() };
  const next = [row, ...readQuestions(storage).filter((item) => item && item.q !== key)].slice(0, QUESTION_CACHE_LIMIT);
  const json = JSON.stringify(next);
  try {
    storage.setItem(STORAGE_KEY, json);
  } catch {
    if (typeof overflow === "function") overflow(json);
  }
  return next;
}

const IDB_NAME = "rrm-questions";

/** IndexedDB when localStorage refuses the write. `db` is the browser `indexedDB` or a test double. */
export function writeOverflow(db, json) {
  return idbStore(db, "readwrite", (store) => store.put(json, STORAGE_KEY));
}

export function readOverflow(db) {
  return idbStore(db, "readonly", (store) => store.get(STORAGE_KEY)).then(
    (value) => (typeof value === "string" ? value : null),
    () => null,
  );
}

function idbStore(db, mode, op) {
  return new Promise((resolve, reject) => {
    if (!db || typeof db.open !== "function") {
      resolve(null);
      return;
    }
    const open = db.open(IDB_NAME, 1);
    open.onupgradeneeded = () => {
      const base = open.result;
      if (!base.objectStoreNames.contains("kv")) base.createObjectStore("kv");
    };
    open.onerror = () => reject(open.error || new Error("idb"));
    open.onsuccess = () => {
      try {
        const tx = open.result.transaction("kv", mode);
        const req = op(tx.objectStore("kv"));
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error || new Error("idb"));
      } catch (err) {
        reject(err);
      }
    };
  });
}

/** encontrado → preparando → listo / falló. `missing` still means the index hit is known. */
export function phaseOf(status) {
  if (status === "done" || status === "abstract_only") return { id: "listo", label: "listo" };
  if (status === "failed") return { id: "fallo", label: "falló" };
  if (status === "queued" || status === "parsing") return { id: "preparando", label: "preparando" };
  return { id: "encontrado", label: "encontrado" };
}
