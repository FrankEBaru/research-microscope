// Client for the live burst and reader. Plain JS so `node --test` can import it.
// NEXT_PUBLIC_* is inlined by the static export. Empty URLs keep the curated mock.

const BURST = process.env.NEXT_PUBLIC_BURST_URL || "";
const READER = process.env.NEXT_PUBLIC_READER_URL || "";
const TOKEN = process.env.NEXT_PUBLIC_RRM_DEMO_TOKEN || "";

export function liveEnabled() {
  return Boolean(BURST) && Boolean(READER);
}

if (liveEnabled() && !TOKEN) {
  throw new Error("NEXT_PUBLIC_RRM_DEMO_TOKEN is empty");
}

export function paperKey(paper) {
  return typeof paper.corpusid === "number" ? String(paper.corpusid) : paper.arxivId;
}

export function figureUrl(id, name) {
  if (String(name).startsWith("/")) return name;
  if (!liveEnabled()) return `/papers/${id}/${name}`;
  return `${READER}/file?id=${id}&name=${encodeURIComponent(name)}&k=${TOKEN}`;
}

export function refText(x, xref) {
  const label = x.label || "";
  if (x.number != null) return String(label).startsWith("eq") ? `(${x.number})` : String(x.number);
  return (xref && xref[label]) || label;
}

export function eqTex(b) {
  return b.number != null ? `${b.tex}\\tag{${b.number}}` : b.tex;
}

async function getJson(url) {
  const res = await fetch(url, { headers: { "X-RRM-Demo": TOKEN } });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

export function burst(q) {
  return getJson(`${BURST}/burst?q=${encodeURIComponent(q)}&n=10`);
}

export function status(ids) {
  return getJson(`${READER}/status?ids=${ids.join(",")}`);
}

export function paper(id) {
  return getJson(`${READER}/paper?id=${encodeURIComponent(id)}`);
}
