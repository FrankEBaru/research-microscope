// Timeline of work the page already started. No extra server round-trip.

export function createDevLog(now = () => (typeof performance !== "undefined" ? performance.now() : Date.now())) {
  let n = 0;
  const steps = [];
  return {
    steps,
    begin(name, detail = "") {
      const id = ++n;
      steps.push({ id, name: String(name), detail: detail ? String(detail) : "", state: "waiting", t0: now(), t1: null });
      return id;
    },
    finish(id, state, detail) {
      const row = steps.find((step) => step.id === id);
      if (!row) return;
      row.state = state === "error" ? "error" : "ok";
      row.t1 = now();
      if (detail) row.detail = String(detail);
    },
    line(row, clock = now()) {
      const end = row.t1 == null ? clock : row.t1;
      const ms = Math.max(0, Math.round(end - row.t0));
      const mark = row.state === "ok" || row.state === "error" ? row.state : "waiting";
      return `${row.name} — ${ms} ms — ${mark}${row.detail ? ` — ${row.detail}` : ""}`;
    },
  };
}

let bound = null;

export function bindDevLog(log) {
  bound = log || null;
}

export function devBegin(name, detail) {
  return bound ? bound.begin(name, detail) : 0;
}

export function devFinish(id, state, detail) {
  if (bound) bound.finish(id, state, detail);
}
