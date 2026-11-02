// Camino de lectura. El padre de un paso es la visita anterior. El mismo paper no se duplica.

export function pushVisit(stack, id, porQue) {
  const nextId = String(id || "");
  const prev = Array.isArray(stack) ? stack : [];
  if (!nextId) return prev;
  const cur = prev.length ? prev[prev.length - 1] : null;
  if (cur && cur.id === nextId) return prev;
  return [...prev, { id: nextId, porQue: porQue || "", padre: cur ? cur.id : null }];
}

export function resolveCite(key, citeMap) {
  const raw = String(key || "");
  const direct = /^s2:(\d+)$/.exec(raw);
  if (direct) return direct[1];
  const hit = citeMap && citeMap[raw];
  const mapped = /^s2:(\d+)$/.exec(String(hit || ""));
  return mapped ? mapped[1] : "";
}

export function popVisit(stack) {
  const prev = Array.isArray(stack) ? stack : [];
  if (prev.length <= 1) return [];
  return prev.slice(0, -1);
}

export function alignVisit(stack, id) {
  const cur = String(id || "");
  const prev = Array.isArray(stack) ? stack : [];
  if (!cur || !prev.length || String(prev[prev.length - 1].id) === cur) return prev;
  const idx = prev.map((step) => String(step.id)).lastIndexOf(cur);
  return idx < 0 ? [] : prev.slice(0, idx + 1);
}

export function mergeLabels(papers, body) {
  if (!body || body.ok === false) return papers || [];
  const by = body.by_id || {};
  const next = (papers || []).map((paper) => {
    const extra = by[String(paper.corpusid)] || {};
    const authors = Array.isArray(extra.authors) && extra.authors.length ? extra.authors : paper.authors;
    return {
      ...paper,
      ...(authors ? { authors } : {}),
      abstract: extra.abstract || paper.abstract || "",
      tldr: paper.tldr || extra.tldr || "",
      survey: Boolean(extra.survey),
      retracted: extra.retracted === true,
      retraction: extra.retraction || "",
    };
  });
  const add = body.survey_paper;
  if (add && Number.isInteger(add.corpusid) && !next.some((paper) => paper.corpusid === add.corpusid)) {
    next.push({ ...add, survey: true });
  }
  return next;
}
