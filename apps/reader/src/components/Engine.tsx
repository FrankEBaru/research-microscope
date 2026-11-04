"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Paper } from "@/lib/types";
import { Rich } from "@/lib/math";
import { Coverage, ProvChip } from "./Bits";
import PaperView, { plainOf } from "./Paper";
import MapView from "./MapView";
import Panorama from "./Panorama";
import { modelGrowth, tokenGrowth } from "@/lib/scaling.js";
import { burst, curatedContent, curatedPaper, explain, groupNames, keepOpened, labels as fetchLabels, liveEnabled, paperKey, paper as fetchPaper, prepare, recordedQueries, settled, status as fetchStatus, subtopics as fetchSubtopics, warm } from "@/lib/backend.js";
import { classify, storageFault } from "@/lib/faults.js";
import { coreMode } from "@/lib/features.js";
import { applyGroupNames, groupPacks, mapPapers, pinPoint } from "@/lib/layout.js";
import { alignVisit, mergeLabels, popVisit, pushVisit } from "@/lib/path.js";
import { pathOf } from "./atlas/Card";
import { EXPLORE_KEY, pickExplore, readExploreFor, recordVisit, whyLabel } from "@/lib/explore.js";
import { normalizeQuestion, phaseOf, readOverflow, readQuestions, recallQuestion, rememberQuestion, writeOverflow } from "@/lib/qcache.js";
import { bindDevLog, createDevLog } from "@/lib/devlog.js";
import { Boundary, DiagPanel, useDebug } from "./faults";
import TopBar from "./screens/TopBar";
import StartScreen from "./screens/StartScreen";
import MapScreen from "./screens/MapScreen";
import ReaderFrame from "./screens/ReaderFrame";
import type { AtlasCtx } from "./screens/types";

type Route = { q?: string; c?: string; p?: string; b?: string };
const parse = (h: string): Route => {
  const parts = h.replace(/^#\/?/, "").split("/").filter(Boolean);
  const r: any = {};
  for (let i = 0; i + 1 < parts.length; i += 2) r[parts[i]] = decodeURIComponent(parts[i + 1]);
  return r;
};
const fmt = (r: Route) => "#/" + (["q", "c", "p", "b"] as const).filter((k) => r[k]).map((k) => `${k}/${encodeURIComponent(r[k]!)}`).join("/");

function beat(phase: string, since: number) {
  const tail = ` ${Math.max(0, since)} s`;
  if (phase === "wake") return `waking the search engine: loading the paper index into memory (the first time takes about 1–2 min)…${tail}`;
  if (phase === "layout") return `arranging the map…${tail}`;
  return `finding papers…${tail}`;
}

function openGroup(result: any, id: string) {
  const point = (result?.layout?.points || []).find((item: any) => String(item.corpusid) === String(id));
  if (!point || point.cluster == null) return null;
  const found = (result?.layout?.groups || []).find((group: any) => String(group.id) === String(point.cluster));
  if (!found) return null;
  const n = ((Number(point.cluster) % 6) + 6) % 6 + 1;
  const name = String(found.name || "").trim();
  return { id: String(found.id), n, name: name || "Group" };
}

export default function Engine() {
  const [route, setRoute] = useState<Route>({});
  const [content, setContent] = useState<any>(null);
  const [papers, setPapers] = useState<Record<string, Paper>>({});
  const [err, setErr] = useState<string>("");
  const [companion, setCompanion] = useState(false); // opt-in: apagado por defecto y sin persistencia
  const live = liveEnabled();
  const core = coreMode();
  const [draft, setDraft] = useState("");
  const [recorded, setRecorded] = useState<string[]>([]);
  const [liveQ, setLiveQ] = useState("");
  const [topics, setTopics] = useState<string[] | null>(null);
  const [liveOn, setLiveOn] = useState(false);
  const [pending, setPending] = useState(false);
  const [engine, setEngine] = useState(live ? "preparando" : "listo");
  const [liveResult, setLiveResult] = useState<any>(null);
  const [liveErr, setLiveErr] = useState("");
  const [liveCode, setLiveCode] = useState("");
  const debug = useDebug();
  const [impatient, setImpatient] = useState(false); // hay papers que no terminan: se puede armar con los ya leídos
  const [forced, setForced] = useState(false);
  const [rowState, setRowState] = useState<Record<string, any>>({});
  const [opened, setOpened] = useState<any>(null);
  const [asList, setAsList] = useState(false);
  const [camino, setCamino] = useState<{ id: string; porQue: string; padre: string | null }[]>([]);
  const [laneId, setLaneId] = useState("");
  const caminoRef = useRef(camino);
  caminoRef.current = camino;
  const [explore, setExplore] = useState<{ q: string; nodes: any[]; edges: any[] }>({ q: "", nodes: [], edges: [] });
  const [labelNote, setLabelNote] = useState("");
  const [phase, setPhase] = useState("");
  const [since, setSince] = useState(0);
  const [openLine, setOpenLine] = useState("");
  const searchGen = useRef(0);
  const lastOk = useRef(0);
  const burstReady = useRef(0); // RRM-47: la búsqueda respondió /warm (antes «listo» venía del lector)
  const wakeAt = useRef(Date.now());
  const [devTick, setDevTick] = useState(0);
  const devRef = useRef<ReturnType<typeof createDevLog> | null>(null);
  if (!devRef.current) devRef.current = createDevLog();
  const dev = devRef.current;
  const note = useCallback((name: string, detail?: string) => {
    const id = dev.begin(name, detail || "");
    setDevTick((n) => n + 1);
    return id;
  }, [dev]);
  const done = useCallback((id: number, state: string, detail?: string) => {
    dev.finish(id, state, detail);
    setDevTick((n) => n + 1);
  }, [dev]);
  const fail = useCallback((e: any) => {
    setLiveErr(explain(e));
    setLiveCode(e?.code || classify(e));
  }, []);

  useEffect(() => {
    bindDevLog({
      begin: (name: string, detail?: string) => { const id = dev.begin(name, detail || ""); setDevTick((n) => n + 1); return id; },
      finish: (id: number, state: string, detail?: string) => { dev.finish(id, state, detail); setDevTick((n) => n + 1); },
    });
  }, [dev]);

  useEffect(() => {
    if (!live || process.env.NEXT_PUBLIC_RRM_OFFLINE !== "1") return;
    let stop = false;
    recordedQueries().then((rows: string[]) => { if (!stop) setRecorded(rows); });
    return () => { stop = true; };
  }, [live]);

  useEffect(() => {
    const db = typeof indexedDB === "undefined" ? null : indexedDB;
    let stop = false;
    readOverflow(db).then((raw) => {
      if (stop || !raw) return;
      try {
        if (!localStorage.getItem("rrm.questions.v1")) localStorage.setItem("rrm.questions.v1", raw);
      } catch (e) { storageFault(e, "localStorage"); }
    }).catch((e) => storageFault(e, "IndexedDB"));
    return () => { stop = true; };
  }, []);

  useEffect(() => {
    const running = phase || (engine === "preparando" && !liveResult);
    if (!running) return;
    const t0 = Date.now();
    setSince(0);
    const id = window.setInterval(() => setSince(Math.round((Date.now() - t0) / 1000)), 400);
    return () => window.clearInterval(id);
  }, [phase, engine, liveResult]);

  useEffect(() => {
    if (!live) { setEngine("listo"); return; }
    let stop = false;
    const burstStep = note("motor de ráfaga", "GET /warm");
    const readerStep = note("motor de lectura", "GET /warm");
    warm("burst").then(
      () => { burstReady.current = Date.now(); if (!stop) { done(burstStep, "ok", "listo"); setEngine("listo"); } },
      (err: any) => { if (!stop) { done(burstStep, "error", explain(err)); setEngine("listo"); } },
    );
    warm("reader").then(
      () => { if (!stop) done(readerStep, "ok", "listo"); },
      (err: any) => { if (!stop) done(readerStep, "error", explain(err)); },
    );
    return () => { stop = true; };
  }, [live, note, done]);

  useEffect(() => {
    const on = () => setRoute(parse(location.hash));
    on(); window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    // B1 en vivo no usa los papers curados (el Release viejo). Atlas, lector y caja salen del backend.
    if (live && core) return;
    (async () => {
      try {
        const c = await curatedContent();
        setContent(c);
        const ids = new Set<string>();
        c.map.questions.forEach((q: any) => q.clusters.forEach((cl: any) => cl.papers.forEach((p: any) => ids.add(p.id))));
        const got = await Promise.all([...ids].map(async (id) => [id, await curatedPaper(id)] as const));
        setPapers(Object.fromEntries(got));
      } catch (e: any) {
        setErr("No se encontraron los datos. Ejecuta `npm run data` (descarga los papers de arXiv; no se commitean).");
      }
    })();
  }, [live, core]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || /INPUT|TEXTAREA/.test((e.target as HTMLElement).tagName)) return;
      if (!core && (e.key === "c" || e.key === "C")) setCompanion((v) => !v);
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [core]);

  const go = useCallback((r: Route) => { location.hash = fmt(r); window.scrollTo({ top: 0 }); }, []);
  const liveIds: string[] = (liveResult?.papers || []).slice(0, 10).map((p: any) => paperKey(p));
  const liveName = (id: string) => { const p = (liveResult?.papers || []).find((x: any) => paperKey(x) === id); return p ? `${String(p.title || id).slice(0, 28)}${p.year ? ` ${p.year}` : ""}` : id; };
  const liveId = live && route.p && /^\d+$/.test(route.p) ? route.p : "";
  const promoteBurst = useCallback((first?: string) => {
    const ids = (liveResult?.papers || []).slice(0, 10).map((p: any) => p.corpusid).filter((id: any) => typeof id === "number");
    const head = Number(first);
    const ordered = Number.isInteger(head) ? [head, ...ids.filter((id: number) => id !== head)] : ids;
    if (ordered.length) prepare(ordered, true).catch(() => {});
  }, [liveResult]);
  const titleFor = useCallback((id: string) => {
    const hit = (liveResult?.papers || []).find((item: any) => paperKey(item) === id);
    if (hit?.title) return String(hit.title);
    if (opened?.paper && paperKey(opened.paper) === id && opened.paper.title) return String(opened.paper.title);
    const curated = papers?.[id];
    return curated?.title ? String(curated.title) : "";
  }, [liveResult, opened, papers]);
  const abrir = useCallback((id: string, porQue: string) => {
    const key = String(id || "");
    if (!key) return;
    const prev = caminoRef.current || [];
    const from = prev.length ? prev[prev.length - 1].id : "";
    try {
      const graph = recordVisit(localStorage, liveQ, {
        id: key, title: titleFor(key), from, porQue, at: Date.now(),
      }, (json: string) => { writeOverflow(indexedDB, json, EXPLORE_KEY).catch((e) => storageFault(e, "IndexedDB")); });
      setExplore(graph);
    } catch (e) { storageFault(e, "localStorage"); }
    setCamino(pushVisit(prev, key, porQue));
    promoteBurst(key);
    if (key === liveId) return;
    go({ p: key });
  }, [go, liveId, liveQ, promoteBurst, titleFor]);
  useEffect(() => {
    if (!liveId) return;
    setCamino((prev) => alignVisit(prev, liveId));
  }, [liveId]);
  const volver = () => {
    const next = popVisit(camino);
    setCamino(next);
    if (next.length) go({ p: next[next.length - 1].id });
    else go({});
  };
  const irPaso = (id: string) => {
    const key = String(id || "");
    if (!key) return;
    const prev = caminoRef.current || [];
    const idx = prev.map((step) => String(step.id)).lastIndexOf(key);
    if (idx >= 0) {
      setCamino(prev.slice(0, idx + 1));
      if (key !== liveId) go({ p: key });
      else window.scrollTo({ top: 0 });
      return;
    }
    abrir(key, "from the path");
  };
  const home = () => {
    setLiveOn(false);
    setPending(false);
    setPhase("");
    setLiveErr("");
    setLiveCode("");
    setDraft("");
    go({});
  };

  useEffect(() => {
    let stop = false;
    try {
      const local = readExploreFor(localStorage, liveQ, liveId);
      if ((local.nodes || []).length) { setExplore(local); return; }
    } catch (e) { storageFault(e, "localStorage"); }
    readOverflow(indexedDB, EXPLORE_KEY).then((json) => {
      if (stop || !json) return;
      try {
        const picked = pickExplore(JSON.parse(json), liveQ, liveId);
        if (picked.nodes.length) setExplore(picked);
      } catch (e) { storageFault(e, "IndexedDB"); }
    }).catch((e) => storageFault(e, "IndexedDB"));
    return () => { stop = true; };
  }, [liveQ, liveId]);

  useEffect(() => {
    if (!liveOn || !liveResult) return;
    const ids = (liveResult.papers || []).slice(0, 10).map((p: any) => p.corpusid).filter((id: any) => typeof id === "number");
    if (!ids.length) return;
    let stop = false;
    const tick = async () => {
      try {
        const body = await fetchStatus(ids, liveQ);
        if (stop) return;
        const map: Record<string, any> = {};
        for (const row of body.papers || []) map[String(row.id)] = row;
        setRowState(map); setLiveErr("");
        if (ids.every((id: number) => settled(map[String(id)]?.status))) return;
      } catch (e: any) {
        if (!stop) fail(e);
      }
      if (!stop) window.setTimeout(tick, 1500);
    };
    tick();
    const patience = window.setTimeout(() => setImpatient(true), (window as any).__RRM_PATIENCE_MS ?? 90000);
    return () => { stop = true; window.clearTimeout(patience); };
  }, [liveOn, liveResult, liveQ]);

  useEffect(() => {
    if (!liveResult || !liveQ) return;
    if (liveResult.provisional) return; // RRM-48: búsqueda sin el índice de títulos; no se guarda
    const keep = () => {
      try { rememberQuestion(localStorage, liveQ, { result: liveResult, states: rowState }, (json: string) => { writeOverflow(indexedDB, json).catch((e) => storageFault(e, "IndexedDB")); }); }
      catch (e) { storageFault(e, "localStorage"); }
    };
    keep();
  }, [liveResult, liveQ, rowState]);

  useEffect(() => {
    if (core || !liveOn || !liveQ) return;
    let stop = false;
    fetchSubtopics(liveQ).then(
      (body: any) => { if (!stop) setTopics(Array.isArray(body?.subtopics) ? body.subtopics : []); },
      () => { if (!stop) setTopics([]); },
    );
    return () => { stop = true; };
  }, [liveOn, liveQ]);

  useEffect(() => {
    if (!liveId) { setOpened(null); setOpenLine(""); return; }
    let stop = false;
    const t0 = Date.now();
    setOpenLine("Opening the paper… 0 s");
    const clock = window.setInterval(() => {
      const sec = Math.round((Date.now() - t0) / 1000);
      setOpenLine((cur) => (cur.startsWith("Reading sections") ? `Reading sections… ${sec} s` : `Opening the paper… ${sec} s`));
    }, 400);
    let sig = "";
    let citedRefs = -1;
    const sectionsIn = (body: any) => ((body?.paper || {}).blocks || []).some((block: any) => block && (block.kind === "h" || (block.kind === "p" && !block.abs)));
    const quiet = () => { window.clearInterval(clock); setOpenLine(""); };
    const apply = (body: any) => {
      const doc = body.paper || {};
      const meta = body.meta || {};
      const paper = {
        ...doc,
        authors: doc.authors || [],
        refs: doc.refs || {},
        blocks: doc.blocks || [],
        arxivId: doc.arxivId || "",
        title: doc.title || "",
        date: doc.date || "",
        full: Boolean(doc.full),
        abstract: doc.abstract || "",
        tldr: doc.tldr || "",
        stage: doc.stage || meta.stage,
        source: doc.source || meta.source,
        upgraded_from: doc.upgraded_from || meta.upgraded_from,
        corpusid: typeof doc.corpusid === "number" ? doc.corpusid : Number(liveId),
      };
      setOpened((prev) => {
        const same = prev && String(prev.paper?.corpusid) === String(paper.corpusid);
        if (same && !paper.citeMap && prev.paper?.citeMap) {
          paper.citeMap = prev.paper.citeMap;
          if (!paper.graphRefs) paper.graphRefs = prev.paper.graphRefs;
        }
        if (same && keepOpened(prev.paper, paper) !== paper) return prev;
        return {
          paper,
          remote: {
            status: body.status,
            stage: doc.stage || meta.stage,
            reason: meta.reason,
            source: doc.source || meta.source,
            pdf: Boolean(meta.pdf),
            oa_pdf: meta.oa_pdf || "",
            arxiv: meta.arxiv || doc.arxivId || "",
          },
        };
      });
      const n = paper.refs && typeof paper.refs === "object" ? Object.keys(paper.refs).length : 0;
      if (body?.cites === "pending" && n > 0 && n !== citedRefs) {
        citedRefs = n;
        fetchPaper(liveId, { cites: true }).then((next) => { if (!stop) apply(next); }).catch(() => {});
      }
      if (sectionsIn({ paper }) || settled(body.status)) quiet();
      else setOpenLine((cur) => (String(cur).startsWith("Reading sections") ? cur : "Reading sections…"));
      const blocks = doc.blocks || [];
      const hasBody = Boolean(doc.full) || meta.source === "latex" || meta.source === "ocr"
        || blocks.some((block: any) => block && (block.kind === "h" || block.kind === "eq" || (block.kind === "p" && !block.abs)));
      if (hasBody) {
        setRowState((prev) => ({ ...prev, [liveId]: { ...(prev[liveId] || {}), id: Number(liveId), text: true } }));
      }
    };
    const signature = (body: any) => {
      const meta = body.meta || {};
      const doc = body.paper || {};
      return `${doc.stage || meta.stage || ""}|${body.status || ""}|${doc.upgraded_from || meta.upgraded_from || ""}`;
    };
    const loop = async () => {
      try {
        const st = await fetchStatus([liveId], liveQ);
        if (stop) return;
        const row = (st.papers || [])[0] || {};
        const next = `${row.stage || ""}|${row.status || ""}|${row.upgraded_from || ""}`;
        if (next !== sig) {
          sig = next;
          apply(await fetchPaper(liveId));
        }
        if (settled(row.status)) return;
      } catch (e: any) {
        if (!stop) fail(e);
      }
      if (!stop) window.setTimeout(loop, 2000);
    };
    (async () => {
      try {
        const body = await fetchPaper(liveId);
        if (stop) return;
        sig = signature(body);
        apply(body);
        if (settled(body.status)) return;
      } catch (e: any) {
        if (!stop) fail(e);
      }
      if (!stop) window.setTimeout(loop, 2000);
    })();
    return () => { stop = true; window.clearInterval(clock); };
  }, [liveId, liveQ]);

  const hasResult = Boolean(liveResult);
  useEffect(() => {
    if (pending || !core || !live || liveResult || !route.p) return;
    let rows: any[] = [];
    try { rows = readQuestions(localStorage); } catch (e) { storageFault(e, "localStorage"); rows = []; }
    const hit = rows.find((row) => (row?.payload?.result?.papers || []).some((p: any) => paperKey(p) === route.p));
    if (!hit?.payload?.result) return;
    setLiveQ(hit.q);
    setRowState(hit.payload.states || {});
    setLiveResult(hit.payload.result);
    setLiveOn(true);
  }, [core, live, liveResult, route.p, pending]);
  useEffect(() => {
    if (!core || !liveQ || !hasResult) return;
    let stop = false;
    let timer = 0;
    const run = (attempt: number) => {
      fetchLabels(liveQ).then(
        (body: any) => {
          if (stop) return;
          if (body?.reason === "pending" && attempt < 5) {
            setLabelNote("");
            timer = window.setTimeout(() => run(attempt + 1), 400 * 2 ** attempt);
            return;
          }
          setLabelNote(body?.reason === "network" ? (body.note || "Offline: title only, no survey.") : "");
          setLiveResult((prev) => {
            if (!prev) return prev;
            const papers = mergeLabels(prev.papers || [], body);
            const by = body?.by_id || {};
            const similar = (prev.similar || []).map((paper: any) => {
              const extra = by[String(paper.corpusid)] || {};
              return {
                ...paper,
                abstract: extra.abstract || paper.abstract || "",
                survey: Boolean(extra.survey),
                retracted: extra.retracted === true,
                retraction: extra.retraction || "",
                ...(Array.isArray(extra.authors) && extra.authors.length ? { authors: extra.authors } : {}),
              };
            });
            const layout = body?.survey_paper ? pinPoint(prev.layout, body.survey_paper) : prev.layout;
            return { ...prev, papers, similar, layout };
          });
          const sid = body?.survey_paper?.corpusid;
          if (sid) prepare([sid], false).catch(() => {});
        },
        (err: any) => {
          if (stop) return;
          if (attempt < 4) {
            timer = window.setTimeout(() => run(attempt + 1), 400 * 2 ** attempt);
            return;
          }
          setLabelNote(err?.kind === "network" ? "Offline: title only, no survey." : "");
        },
      );
    };
    run(0);
    return () => { stop = true; window.clearTimeout(timer); };
  }, [core, liveQ, hasResult]);

  const namesKey = liveResult?.group_names && liveQ && !liveResult?.layout?.pending_vectors?.length ? liveQ : "";
  useEffect(() => {
    if (!namesKey || !liveResult?.layout) return;
    const packs = groupPacks(mapPapers(liveResult), liveResult.layout);
    if (!packs.length) return;
    let stop = false;
    // RRM-95: the map is already painted with c-TF-IDF names; Muse names fade in
    // when they arrive. Cached per question for the tab; a slow or failed call
    // leaves the first names in place.
    const cacheKey = `rrm.gnames.${normalizeQuestion(namesKey)}`;
    try {
      const hit = JSON.parse(sessionStorage.getItem(cacheKey) || "null");
      if (Array.isArray(hit) && hit.length) {
        setLiveResult((prev) => (prev ? applyGroupNames(prev, hit) : prev));
        return;
      }
    } catch { /* private mode */ }
    const t0 = performance.now();
    groupNames(packs).then(
      (body: any) => {
        note("group-names", `${Math.round(performance.now() - t0)} ms · ${body?.names?.length || 0} names · $${body?.meta?.cost_usd ?? 0}`);
        if (stop || !body?.enabled || !body?.names?.length) return;
        try { sessionStorage.setItem(cacheKey, JSON.stringify(body.names)); } catch { /* private mode */ }
        setLiveResult((prev) => (prev ? applyGroupNames(prev, body.names) : prev));
      },
      () => { note("group-names", `kept c-TF-IDF after ${Math.round(performance.now() - t0)} ms`); },
    );
    return () => { stop = true; };
  }, [namesKey]);

  const onSearch = async (e: { preventDefault: () => void; query?: string }) => {
    e.preventDefault();
    const q = String(e.query || draft).trim();
    if (!q || pending) return;
    const gen = ++searchGen.current;
    setLiveQ(q); setLiveOn(true); setLiveErr(""); setLiveCode(""); setImpatient(false); setForced(false); setTopics(null); setAsList(false); setLabelNote("");
    setLiveResult(null); setRowState({}); setOpened(null); setCamino([]); setExplore({ q, nodes: [], edges: [] }); setLaneId("");
    go({});
    setPending(true);
    let cached: any = null;
    try { cached = recallQuestion(localStorage, q); } catch (e) { storageFault(e, "localStorage"); cached = null; }
    if (cached?.payload?.result) {
      const step = note("pregunta", normalizeQuestion(q));
      setLiveResult(cached.payload.result);
      setRowState(cached.payload.states || {});
      setPending(false);
      setPhase("");
      done(step, "ok", "caché del navegador");
      go({});
      return;
    }
    setLiveResult(null); setRowState({});
    const warmAt = Math.max(lastOk.current, burstReady.current);
    const cold = !warmAt || Date.now() - warmAt > 8 * 60 * 1000;
    if (cold && engine !== "preparando") wakeAt.current = Date.now();
    setSince(0);
    setPhase(cold ? "wake" : "search");
    const step = note("ráfaga", q);
    try {
      if (cold) {
        try { await warm("burst"); } catch { /* la ráfaga dice si de verdad falló */ }
        if (searchGen.current !== gen) return;
        setSince(0);
        setPhase("search");
      }
      const body = await burst(q);
      if (searchGen.current !== gen) return;
      lastOk.current = Date.now();
      setLiveResult(body);
      setPhase(body?.layout?.pending_vectors?.length ? "layout" : "");
      const bits = body?.seconds ? Object.entries(body.seconds).map(([k, v]) => `${k} ${v}s`).join(", ") : "";
      done(step, "ok", body?.cached ? `caché del servidor${bits ? ` — ${bits}` : ""}` : bits);
      go({});
    } catch (err: any) {
      if (searchGen.current !== gen) return;
      setPhase("");
      fail(err);
      done(step, "error", explain(err));
    } finally {
      if (searchGen.current === gen) setPending(false);
    }
  };
  const wantThis = (id: string) => {
    const step = note("quiero leer este", id);
    const key = String(id);
    setRowState((prev) => {
      const cur = prev[key];
      // Ready (done or abstract-only) stays Ready. Queued would show Preparing.
      if (cur?.status === "done" || cur?.status === "abstract_only") return prev;
      return { ...prev, [key]: { ...(cur || {}), id: Number(id), status: "queued" } };
    });
    prepare([Number(id)], true).then(
      () => done(step, "ok", "al frente de la cola"),
      (err: any) => done(step, "error", explain(err)),
    );
  };
  const backToCurated = () => {
    setLiveOn(false); setLiveQ(""); setLiveResult(null); setRowState({}); setTopics(null); setOpened(null); setPending(false); setLiveErr(""); setImpatient(false); setForced(false);
    go({});
  };
  const shownQ = String(liveResult?.query || liveQ || "");
  const say = (p: string) => beat(p, p === "wake" ? Math.round((Date.now() - wakeAt.current) / 1000) : since);
  const questions = content?.map.questions || [];
  const q = questions.find((x: any) => x.id === (route.q || questions[0]?.id)) || questions[0];
  const cluster = q?.clusters.find((c: any) => c.id === route.c);
  const paper = route.p ? papers[route.p] : undefined;
  const level = route.p ? 3 : route.c ? 2 : 1;

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (level === 3) go({ q: q?.id, c: route.c }); else if (level === 2) go({ q: q?.id });
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [level, q, route.c, go]);

  const curatedReady = Boolean(content) && Object.keys(papers).length > 0;
  if (err && !(live && core)) return <main className="center-msg"><p>{err}</p></main>;
  if (!curatedReady && !(live && core)) return <main className="center-msg"><p>Cargando…</p></main>;

  const steps = q ? [
    { n: 1, label: "Área", sub: q.text, on: () => go({ q: q.id }) },
    { n: 2, label: "Cluster", sub: cluster?.title, on: cluster ? () => go({ q: q.id, c: cluster.id }) : undefined },
    { n: 3, label: "Paper", sub: paper ? paper.title : undefined, on: undefined },
  ] : [];

  const atlasCtx: AtlasCtx = {
    papers: liveResult ? mapPapers(liveResult) : [],
    edges: liveResult?.edges || [],
    layout: liveResult?.layout,
    states: rowState,
    query: shownQ,
    explore,
    openId: liveId,
    laneId,
    onOpen: abrir,
    onWant: wantThis,
  };
  const onLayout = (next: any) => { setLiveResult((prev) => (prev ? { ...prev, layout: next } : prev)); if (!next?.pending_vectors?.length) setPhase((cur) => (cur === "layout" ? "" : cur)); };
  const back = !core ? <button type="button" className="link" onClick={backToCurated}>Back to the curated burst</button> : null;
  const backBtn = core && liveId
    ? <button type="button" className="top-back press" aria-label="Back" onClick={() => (camino.length > 1 ? volver() : go({}))}>←</button>
    : null;
  const jump = (() => {
    const top = camino[camino.length - 1];
    const why = top?.padre ? whyLabel(top.porQue) : "";
    return why ? <p className="jump-why">Jump: {why}</p> : null;
  })();
  const groupNow = liveId ? openGroup(liveResult, liveId) : null;
  const crumb = core && (liveOn || liveId) ? {
    question: shownQ,
    onAtlas: () => { setLaneId(""); go({}); },
    onGroup: groupNow ? () => { setLaneId(groupNow.id); go({}); } : undefined,
    group: groupNow,
    paper: liveId ? titleFor(liveId) : "",
    paperId: liveId,
    steps: pathOf(explore).map((step) => {
      const known = step.title && !/^\d+$/.test(step.title) ? step.title : titleFor(step.id);
      return { ...step, title: known && !/^\d+$/.test(known) ? known : "Paper" };
    }),
    onStep: irPaso,
  } : null;
  const frame = {
    back, openLine, liveErr, liveCode, debug,
    content, focus: route.b, companion, onHideCompanion: () => setCompanion(false), core,
    burstIds: (liveResult?.papers || []).slice(0, 10).map((p: any) => paperKey(p)),
    map: liveResult ? { papers: mapPapers(liveResult), edges: liveResult.edges || [], layout: liveResult.layout } : null,
    explore, openId: liveId, onOpenPaper: abrir, onPromote: () => promoteBurst(liveId), atlasCtx,
  };

  return (
    <>
      <TopBar core={core} live={live} liveOn={liveOn} liveId={liveId} steps={steps} level={level} draft={draft} setDraft={setDraft} onSearch={onSearch} companion={companion} setCompanion={setCompanion} onHome={home} crumb={crumb} back={backBtn} recorded={recorded} />

      <main key={`${level}-${route.c}-${route.p}`} className="zoom-in">
        {live && (liveOn || liveId) && liveId && opened && <Boundary name="reader"><ReaderFrame {...frame} opened={opened} /></Boundary>}
        {live && (liveOn || liveId) && liveId && !opened && <Boundary name="reader"><ReaderFrame {...frame} opened={null} /></Boundary>}
        {live && core && !liveOn && !liveId && (
          <Boundary name="start"><StartScreen draft={draft} setDraft={setDraft} onSearch={onSearch} pending={pending} engine={engine} phase={phase} recorded={recorded} /></Boundary>
        )}
        {live && liveOn && !liveId && (
          <Boundary name="map"><MapScreen core={core} shownQ={shownQ} topics={topics} liveResult={liveResult} phase={phase} engine={engine} say={say} liveErr={liveErr} liveCode={liveCode} debug={debug} pending={pending} asList={asList} setAsList={setAsList} labelNote={labelNote} liveIds={liveIds} impatient={impatient} forced={forced} setForced={setForced} liveQ={liveQ} liveName={liveName} go={go} backToCurated={backToCurated} atlasCtx={atlasCtx} onLayout={onLayout} jump={jump} /></Boundary>
        )}
        {!(live && core) && !(live && (liveOn || liveId)) && level === 1 && <Area q={q} questions={questions} papers={papers} go={go} content={content} core={core} />}
        {!(live && core) && !(live && (liveOn || liveId)) && level === 2 && cluster && <Cluster q={q} cl={cluster} papers={papers} go={go} />}
        {!(live && core) && !(live && (liveOn || liveId)) && level === 3 && paper && <PaperView paper={paper} content={content} focus={route.b} companion={core ? false : companion} onHideCompanion={() => setCompanion(false)} showInstrument={!core} showCrops={!core} core={core} onOpenPaper={abrir} />}
        {!(live && (liveOn || liveId)) && level === 3 && !paper && <p className="center-msg">Paper no encontrado.</p>}
      </main>

      {!(core && live) && (
        <footer className="legend">
          <span>Procedencia:</span>
          <ProvChip kind="paper" /><ProvChip kind="curado" /><ProvChip kind="calculo" /><ProvChip kind="simulado" />
          <span className="legend-note">Papers: arXiv (atribución en cada paper). Lo simulado es maqueta del motor, aún no conectado.</span>
        </footer>
      )}
      <DiagPanel dev={dev} data-devlog={devTick} />
    </>
  );
}

/* ---------- Nivel 1: área ---------- */
function Area({ q, questions, papers, go, content, core }: any) {
  const [view, setView] = useState<"mapa" | "tarjetas" | "panorama">("mapa");
  useEffect(() => { if (window.innerWidth < 700) setView("tarjetas"); }, []); // el mapa necesita ancho: en pantallas angostas se empieza por las tarjetas
  return (
    <section className="lvl lvl1">
      <p className="eyebrow">Nivel 1 · Área</p>
      <div className="qtabs">{questions.map((x: any) => <button key={x.id} className={x.id === q.id ? "on" : ""} onClick={() => go({ q: x.id })}>{x.text}</button>)}</div>
      <h1 className="question">{q.text}</h1>
      <p className="sub"><ProvChip kind="curado" text="ráfaga de ejemplo curada a mano" /> No es la salida del motor de ráfaga: es el formato que ese motor llenará.</p>
      <div className="view-toggle" role="tablist" aria-label="View"><button className={view === "mapa" ? "on" : ""} onClick={() => setView("mapa")}>Map</button><button className={view === "tarjetas" ? "on" : ""} onClick={() => setView("tarjetas")}>Cards</button>{!core && <button className={view === "panorama" ? "on" : ""} onClick={() => setView("panorama")}>Panorama</button>}</div>
      {view === "mapa" && <MapView q={q} papers={papers} go={go} />}
      {!core && view === "panorama" && <Panorama q={q} papers={papers} content={content} go={go} />}
      {view === "tarjetas" && <div className="clusters">
        {q.clusters.map((c: any, i: number) => {
          const have = c.papers.filter((p: any) => papers[p.id]?.full).length;
          return (
            <button key={c.id} className="card cluster-card" onClick={() => go({ q: q.id, c: c.id })}>
              <span className="card-n">{i + 1}</span>
              <h2>{c.title}</h2>
              <div className="chips"><ProvChip kind="curado" text="título: hipótesis del curador" />{c.tension && <ProvChip kind="curado" text="incluye una tensión" />}</div>
              <ul className="mini-papers">{c.papers.map((p: any) => <li key={p.id}><span>{papers[p.id].title}</span><em>{papers[p.id].authors[0]?.split(" ").pop()} {papers[p.id].date?.slice(0, 4)}</em></li>)}</ul>
              <Coverage have={have} total={c.papers.length} />
              <span className="enter">Acercar →</span>
            </button>
          );
        })}
      </div>}
    </section>
  );
}

/* ---------- Nivel 2: cluster ---------- */
function Cluster({ q, cl, papers, go }: any) {
  const have = cl.papers.filter((p: any) => papers[p.id]?.full).length;
  return (
    <section className="lvl lvl2">
      <p className="eyebrow">Nivel 2 · Cluster · <a href={fmt({ q: q.id })} className="up">← {q.text}</a></p>
      <h1 className="question">{cl.title}</h1>
      <Coverage have={have} total={cl.papers.length} />
      {cl.tension && <Tension t={cl.tension} papers={papers} />}
      <div className="paper-cards">
        {cl.papers.map((cp: any) => {
          const p: Paper = papers[cp.id];
          const fig = cp.figure && p.blocks.find((b) => b.label === cp.figure);
          return (
            <article key={cp.id} className="card pcard">
              <div className="chips"><ProvChip kind="paper" text={`arXiv:${p.arxivId}`} />{!p.full && <ProvChip kind="curado" text="solo abstract" />}</div>
              <h2>{p.title}</h2>
              <p className="authors">{p.authors.slice(0, 3).join(", ")}{p.authors.length > 3 ? " et al." : ""} · {p.date?.slice(0, 4)}</p>
              <div className="oneminute">
                <h3>Vista de un minuto</h3>
                <blockquote><span className="qlab">Aporte, en palabras del abstract</span>«<Rich text={cp.contribution.quote} />»
                  <button className="link" onClick={() => go({ q: q.id, c: cl.id, p: p.arxivId, b: cp.contribution.anchor.blockId })}>ver dónde lo dice →</button></blockquote>
                {fig && (
                  <figure className="thumb"><img src={fig.images[0]} alt={plainOf(fig.caption)} onError={(e) => { (e.currentTarget.closest("figure") || e.currentTarget).setAttribute("hidden", ""); }} /><figcaption><b>Figura 1 del paper</b> · {plainOf(fig.caption)}</figcaption></figure>
                )}
                {cp.pending ? (
                  <blockquote><span className="qlab">Lo que el paper deja pendiente (no declara limitaciones)</span>«<Rich text={cp.pending.quote} />»</blockquote>
                ) : (
                  <p className="muted">Figura 1 y límites declarados: no disponibles en esta ráfaga (solo se leyó el abstract).</p>
                )}
              </div>
              <button className="primary" onClick={() => go({ q: q.id, c: cl.id, p: p.arxivId })}>Abrir el paper →</button>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function Tension({ t, papers }: any) {
  const nm = (id: string) => `${papers[id].authors[0]?.split(" ").pop()} ${papers[id].date?.slice(0, 4)}`;
  return (
    <section className="tension" aria-label="Tensión entre papers">
      <div className="chips"><ProvChip kind="curado" text="tensión curada a mano" /></div>
      <h2>Dos papers recomiendan cosas distintas</h2>
      <div className="tension-cols">
        {[t.a, t.b].map((x: any) => (
          <blockquote key={x.paper}><span className="qlab">{x.label} · {papers[x.paper].date?.slice(0, 4)}</span>«<Rich text={x.quote} />»</blockquote>
        ))}
      </div>
      <p className="tension-nums"><span className="qlab">En números, citados del abstract de {nm(t.numbers.paper)}</span><Rich text={t.numbers.quote} /></p>
      {t.exponents && <TensionSlider t={t} papers={papers} />}
      <h3>Lo que dos trabajos posteriores dicen sobre la diferencia</h3>
      <div className="tension-cols">
        {t.resolution.map((x: any) => (
          <blockquote key={x.paper}><span className="qlab">{nm(x.paper)}</span>«<Rich text={x.quote} />»</blockquote>
        ))}
      </div>
      <p className="muted">Se muestran las frases, sin etiqueta de «apoya» o «contradice»: esa lectura es del lector.</p>
    </section>
  );
}

function TensionSlider({ t, papers }: any) {
  const [e, setE] = useState(1); // cómputo ×10^e
  const x = Math.pow(10, e);
  const rows = [{ label: "Kaplan", a: t.exponents.a, tone: "a" }, { label: "Chinchilla", a: t.exponents.b, tone: "b" }];
  const maxLog = Math.log10(Math.pow(1000, t.exponents.a));
  const bar = (f: number) => `${Math.max(3, (100 * Math.log10(f)) / maxLog)}%`;
  return (
    <div className="tslider">
      <div className="chips"><ProvChip kind="calculo" text="ilustración con los exponentes citados" /></div>
      <label><span>Si el cómputo de entrenamiento se multiplica por <b>×{x >= 100 ? Math.round(x) : x.toFixed(x < 10 ? 1 : 0)}</b>…</span>
        <input type="range" min={0} max={3} step={0.05} value={e} onChange={(ev) => setE(+ev.target.value)} aria-label="Multiplicador de cómputo" /></label>
      <div className="tgrid">
        {rows.map((r) => (
          <div key={r.label} className="trow">
            <b>{r.label}</b><span className="exp">exponente {r.a.toFixed(2)}</span>
            <div className="tbar"><i className={`bar-${r.tone}`} style={{ width: bar(modelGrowth(x, r.a)) }} /><em>tamaño del modelo ×{modelGrowth(x, r.a).toFixed(1)}</em></div>
            <div className="tbar"><i className="bar-tok" style={{ width: bar(tokenGrowth(x, r.a)) }} /><em>tokens de entrenamiento ×{tokenGrowth(x, r.a).toFixed(1)}</em></div>
          </div>
        ))}
      </div>
      <p className="small">Usa solo lo citado: los exponentes de N<sub>óptimo</sub> ∝ C<sup>a</sup> del abstract de {papers[t.numbers.paper].authors[0]?.split(" ").pop()} y la relación FLOPs ≈ 6·N·D de Chinchilla (de ahí tokens ∝ C<sup>1−a</sup>). No es una predicción propia; con N sin embeddings (Kaplan) la relación 6ND es aproximada, y justo ahí está parte de la discrepancia que explican los dos trabajos de abajo.</p>
    </div>
  );
}
