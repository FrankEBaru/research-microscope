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

export function mergeLabels(papers, body) {
  if (!body || body.ok === false) return papers || [];
  const by = body.by_id || {};
  const next = (papers || []).map((paper) => {
    const extra = by[String(paper.corpusid)] || {};
    return {
      ...paper,
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
