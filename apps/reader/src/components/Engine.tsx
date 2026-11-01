"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Paper } from "@/lib/types";
import { Rich } from "@/lib/math";
import { Coverage, ProvChip } from "./Bits";
import PaperView, { plainOf } from "./Paper";
import MapView from "./MapView";
import Panorama, { LiveCoverage } from "./Panorama";
import SimPanorama from "./SimPanorama";
import { modelGrowth, tokenGrowth } from "@/lib/scaling.js";
import { burst, explain, groupNames, keepOpened, labels as fetchLabels, liveEnabled, paperKey, paper as fetchPaper, prepare, settled, status as fetchStatus, subtopics as fetchSubtopics, warm } from "@/lib/backend.js";
import { coreMode } from "@/lib/features.js";
import { applyGroupNames, groupPacks, mapPapers, pinPoint } from "@/lib/layout.js";
import { mergeLabels, popVisit, pushVisit } from "@/lib/path.js";
import { normalizeQuestion, phaseOf, readOverflow, readQuestions, recallQuestion, rememberQuestion, writeOverflow } from "@/lib/qcache.js";
import { bindDevLog, createDevLog } from "@/lib/devlog.js";
import { LiveCircle } from "./MapView";
import LiveMap from "./LiveMap";

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
  if (phase === "wake") return `despertando el motor de búsqueda: sube el índice de papers a memoria (la primera vez tarda ~1–2 min)…${tail}`;
  if (phase === "layout") return `acomodando el mapa…${tail}`;
  return `buscando papers…${tail}`;
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
  const [liveQ, setLiveQ] = useState("");
  const [topics, setTopics] = useState<string[] | null>(null);
  const [liveOn, setLiveOn] = useState(false);
  const [pending, setPending] = useState(false);
  const [engine, setEngine] = useState(live ? "preparando" : "listo");
  const [liveResult, setLiveResult] = useState<any>(null);
  const [liveErr, setLiveErr] = useState("");
  const [impatient, setImpatient] = useState(false); // hay papers que no terminan: se puede armar con los ya leídos
  const [forced, setForced] = useState(false);
  const [rowState, setRowState] = useState<Record<string, any>>({});
  const [opened, setOpened] = useState<any>(null);
  const [devOn, setDevOn] = useState(false);
  const [asList, setAsList] = useState(false);
  const [camino, setCamino] = useState<{ id: string; porQue: string; padre: string | null }[]>([]);
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

  useEffect(() => {
    bindDevLog({
      begin: (name: string, detail?: string) => { const id = dev.begin(name, detail || ""); setDevTick((n) => n + 1); return id; },
      finish: (id: number, state: string, detail?: string) => { dev.finish(id, state, detail); setDevTick((n) => n + 1); },
    });
  }, [dev]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("dev") === "1") setDevOn(true);
    const db = typeof indexedDB === "undefined" ? null : indexedDB;
    let stop = false;
    readOverflow(db).then((raw) => {
      if (stop || !raw) return;
      try {
        if (!localStorage.getItem("rrm.questions.v1")) localStorage.setItem("rrm.questions.v1", raw);
      } catch { /* the memory of this tab is enough */ }
    }).catch(() => {});
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
    (async () => {
      try {
        const c = await (await fetch("/papers/_content.json")).json();
        setContent(c);
        const ids = new Set<string>();
        c.map.questions.forEach((q: any) => q.clusters.forEach((cl: any) => cl.papers.forEach((p: any) => ids.add(p.id))));
        const got = await Promise.all([...ids].map(async (id) => [id, await (await fetch(`/papers/${id}.json`)).json()] as const));
        setPapers(Object.fromEntries(got));
      } catch (e: any) {
        setErr("No se encontraron los datos. Ejecuta `npm run data` (descarga los papers de arXiv; no se commitean).");
      }
    })();
  }, []);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || /INPUT|TEXTAREA/.test((e.target as HTMLElement).tagName)) return;
      if ((e.key === "d" || e.key === "D")) { setDevOn((v) => !v); return; }
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
  const abrir = useCallback((id: string, porQue: string) => {
    const key = String(id || "");
    if (!key) return;
    setCamino((prev) => pushVisit(prev, key, porQue));
    promoteBurst(key);
    if (key === liveId) return;
    go({ p: key });
  }, [go, liveId, promoteBurst]);
  const volver = () => {
    const next = popVisit(camino);
    setCamino(next);
    if (next.length) go({ p: next[next.length - 1].id });
    else go({});
  };

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
        if (!stop) setLiveErr(explain(e));
      }
      if (!stop) window.setTimeout(tick, 1500);
    };
    tick();
    const patience = window.setTimeout(() => setImpatient(true), (window as any).__RRM_PATIENCE_MS ?? 90000);
    return () => { stop = true; window.clearTimeout(patience); };
  }, [liveOn, liveResult, liveQ]);

  useEffect(() => {
    if (!liveResult || !liveQ) return;
    const keep = () => {
      try { rememberQuestion(localStorage, liveQ, { result: liveResult, states: rowState }, (json: string) => { writeOverflow(indexedDB, json).catch(() => {}); }); }
      catch { /* private mode: the list is still on screen */ }
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
    setOpenLine("abriendo el paper… 0 s");
    const clock = window.setInterval(() => {
      const sec = Math.round((Date.now() - t0) / 1000);
      setOpenLine((cur) => (cur.startsWith("leyendo") ? `leyendo secciones… ${sec} s` : `abriendo el paper… ${sec} s`));
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
      else setOpenLine((cur) => (String(cur).startsWith("leyendo") ? cur : "leyendo secciones…"));
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
        if (!stop) setLiveErr(explain(e));
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
        if (!stop) setLiveErr(explain(e));
      }
      if (!stop) window.setTimeout(loop, 2000);
    })();
    return () => { stop = true; window.clearInterval(clock); };
  }, [liveId, liveQ]);

  const hasResult = Boolean(liveResult);
  useEffect(() => {
    if (pending || !core || !live || liveResult || !route.p) return;
    let rows: any[] = [];
    try { rows = readQuestions(localStorage); } catch { rows = []; }
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
          setLabelNote(body?.reason === "network" ? (body.note || "Sin red: solo el título, sin survey.") : "");
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
          setLabelNote(err?.kind === "network" ? "Sin red: solo el título, sin survey." : "");
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
    groupNames(packs).then(
      (body: any) => {
        if (stop || !body?.enabled || !body?.names?.length) return;
        setLiveResult((prev) => (prev ? applyGroupNames(prev, body.names) : prev));
      },
      () => {},
    );
    return () => { stop = true; };
  }, [namesKey]);

  const onSearch = async (e: { preventDefault: () => void }) => {
    e.preventDefault();
    const q = draft.trim();
    if (!q || pending) return;
    const gen = ++searchGen.current;
    setLiveQ(q); setLiveOn(true); setLiveErr(""); setImpatient(false); setForced(false); setTopics(null); setAsList(false); setLabelNote("");
    setPending(true);
    let cached: any = null;
    try { cached = recallQuestion(localStorage, q); } catch { cached = null; }
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
      setLiveErr(explain(err));
      done(step, "error", explain(err));
    } finally {
      if (searchGen.current === gen) setPending(false);
    }
  };
  const wantThis = (id: string) => {
    const step = note("quiero leer este", id);
    setRowState((prev) => ({ ...prev, [id]: { ...(prev[id] || {}), id: Number(id), status: "queued" } }));
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

  return (
    <>
      <header className="topbar">
        <a className="brand" href="#/" onClick={() => window.scrollTo({ top: 0 })}><span className="lens" aria-hidden="true" />Microscopio de lectura</a>
        {!(core && (liveOn || liveId)) && (
          <nav className="scope" aria-label="Nivel de zoom">
            {steps.map((s) => (
              <button key={s.n} className={`step ${level === s.n ? "on" : ""} ${level > s.n ? "past" : ""}`} disabled={!s.on || level === s.n} onClick={s.on} title={s.sub || ""}>
                <span className="dot">{s.n}</span><span className="lbl">{s.label}</span>
              </button>
            ))}
          </nav>
        )}
        {live && !(core && !liveOn && !liveId) && (
          <form className="live-search" onSubmit={onSearch}>
            <input aria-label="Pregunta" title={draft || undefined} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Pregunta" />
            <button type="submit">Buscar</button>
          </form>
        )}
        {!core && <button className="companion-toggle" aria-pressed={companion} onClick={() => setCompanion((v) => !v)} title="Compañero de lectura opcional: ofrece ayuda, nunca interrumpe, no guarda nada (tecla C)">Compañero {companion ? "activado" : "apagado"}</button>}
        {!(live && process.env.NEXT_PUBLIC_RRM_OFFLINE !== "1") && <span className="proto">prototipo · datos locales</span>}
      </header>

      <main key={`${level}-${route.c}-${route.p}`} className="zoom-in">
        {live && (liveOn || liveId) && liveId && opened && (
          <div className="lvl">
            {!core && <button type="button" className="link" onClick={backToCurated}>volver a la ráfaga curada</button>}
            {core && <button type="button" className="link" onClick={volver}>volver</button>}
            {core && camino[camino.length - 1]?.porQue && <p className="jump-why">Salto: {camino[camino.length - 1].porQue}</p>}
            <PaperView paper={opened.paper} content={content || {}} focus={route.b} companion={core ? false : companion} onHideCompanion={() => setCompanion(false)} remote={opened.remote} showInstrument={!core} showCrops={!core} core={core} burstIds={(liveResult?.papers || []).slice(0, 10).map((p: any) => paperKey(p))} map={liveResult ? { papers: mapPapers(liveResult), edges: liveResult.edges || [], layout: liveResult.layout } : null} onOpenPaper={abrir} onPromote={() => promoteBurst(liveId)} />
          </div>
        )}
        {live && (liveOn || liveId) && liveId && !opened && (
          <div className="lvl">
            {!core && <button type="button" className="link" onClick={backToCurated}>volver a la ráfaga curada</button>}
            {core && <button type="button" className="link" onClick={volver}>volver</button>}
            <p className="center-msg">{liveErr ? "No se pudo cargar el paper (se sigue intentando)." : (openLine || "abriendo el paper…")}</p>
            {liveErr && <p className="fail-reason" role="alert">{liveErr}</p>}
          </div>
        )}
        {live && core && !liveOn && !liveId && (
          <section className="lvl ask">
            <p className="eyebrow">Una pregunta</p>
            <h1 className="question">Qué quieres entender</h1>
            <form className="ask-box" onSubmit={onSearch}>
              <input aria-label="Pregunta" title={draft || undefined} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Una pregunta, un título, un tema" autoFocus />
              <button type="submit" disabled={pending || !draft.trim()}>Ver el mapa</button>
            </form>
            {(engine === "preparando" || phase === "wake") && <p className="warm" role="status">{say(phase || "wake")}</p>}
            <p className="sub">Los papers aparecen como puntos en cuanto la ráfaga responde. El tamaño es el puesto. El texto completo de los 10 primeros se prepara después, sin bloquear el mapa.</p>
          </section>
        )}
        {live && liveOn && !liveId && (
          <section className={`lvl ${core ? "lvl-map" : ""}`}>
            {!core && <button type="button" className="link" onClick={backToCurated}>volver a la ráfaga curada</button>}
            <h1 className="question">{shownQ}</h1>
            {!core && topics && <p className="sub" data-subtopics>{topics.length ? <>Subtemas: {topics.join(" · ")}</> : "Esta pregunta no separó subtemas."}</p>}
            {!core && !liveResult && <p className="warm" role="status">{say(phase || (engine === "preparando" ? "wake" : "search"))}</p>}
            {phase === "layout" && liveResult && <p className="warm" role="status">{beat("layout", since)}</p>}
            {core && !liveResult && <div className="platina is-wait" role="status"><p>{say(phase || "search")}</p></div>}
            {liveErr && <p className="fail-reason" role="alert">{liveErr}</p>}
            {core && liveErr && !liveResult && !pending && <div className="platina is-wait"><p>No se pudo armar el mapa.</p></div>}
            {core && liveResult && (liveResult.papers || []).length > 0 && (
              <>
                <div className="view-toggle" role="tablist" aria-label="Vista">
                  <button type="button" className={!asList ? "on" : ""} onClick={() => setAsList(false)}>Mapa</button>
                  <button type="button" className={asList ? "on" : ""} onClick={() => setAsList(true)}>Lista</button>
                </div>
                {labelNote && <p className="muted" role="status">{labelNote}</p>}
                {liveResult.topic_note && <p className="muted" role="status">{liveResult.topic_note}</p>}
                {asList
                  ? <CoreList papers={liveResult.papers || []} states={rowState} onOpen={(id: string) => abrir(id, "nodo del mapa")} onWant={wantThis} />
                  : <LiveMap papers={mapPapers(liveResult)} edges={liveResult.edges || []} layout={liveResult.layout} states={rowState} query={shownQ} onLayout={(next) => { setLiveResult((prev) => (prev ? { ...prev, layout: next } : prev)); if (!next?.pending_vectors?.length) setPhase((cur) => (cur === "layout" ? "" : cur)); }} onOpen={(id: string) => abrir(id, "nodo del mapa")} onWant={wantThis} />}
                <p className="muted small">Datos de papers y citas: Semantic Scholar. LaTeX primero; OCR solo si el paper no tiene LaTeX.</p>
              </>
            )}
            {!core && liveResult && <LiveCoverage ids={(liveResult.papers || []).slice(0, 10).map((p: any) => paperKey(p))} states={rowState} />}
            {!core && liveResult && liveIds.length === 0 && <p className="muted" role="status">La ráfaga no encontró papers para esta pregunta. Prueba con otras palabras.</p>}
            {core && liveResult && (liveResult.papers || []).length === 0 && <p className="muted" role="status">La ráfaga no encontró papers para esta pregunta. Prueba con otras palabras.</p>}
            {!core && liveResult && liveIds.length > 0 && !liveIds.every((id: string) => settled(rowState[id]?.status)) && impatient && !forced && (
              <p className="muted small" role="status">Algunos papers siguen en cola o leyéndose. <button type="button" className="link" onClick={() => setForced(true)}>Armar el Panorama con los ya leídos</button> (los que faltan no cuentan como «no lo dice»).</p>
            )}
            {!core && liveResult && liveIds.length > 0 && (forced || liveIds.every((id: string) => settled(rowState[id]?.status))) && (
              <SimPanorama key={`${liveQ}|${forced}`} autorun question={liveQ} ids={liveIds} states={rowState} getDoc={async (id: string) => { try { return (await fetchPaper(id)).paper; } catch { return null; } }} nameOf={liveName} open={(id, b) => go({ p: id, b })} />
            )}
            {!core && liveResult && <LiveCircle papers={liveResult.papers || []} edges={liveResult.edges || []} states={rowState} onOpen={(id) => go({ p: id })} />}
          </section>
        )}
        {!(live && core) && !(live && (liveOn || liveId)) && level === 1 && <Area q={q} questions={questions} papers={papers} go={go} content={content} core={core} />}
        {!(live && core) && !(live && (liveOn || liveId)) && level === 2 && cluster && <Cluster q={q} cl={cluster} papers={papers} go={go} />}
        {!(live && core) && !(live && (liveOn || liveId)) && level === 3 && paper && <PaperView paper={paper} content={content} focus={route.b} companion={core ? false : companion} onHideCompanion={() => setCompanion(false)} showInstrument={!core} showCrops={!core} core={core} onOpenPaper={abrir} />}
        {!(live && (liveOn || liveId)) && level === 3 && !paper && <p className="center-msg">Paper no encontrado.</p>}
      </main>

      <footer className="legend">
        {core && live ? (
          <span className="legend-note">Papers y citas: Semantic Scholar.</span>
        ) : (
          <>
            <span>Procedencia:</span>
            <ProvChip kind="paper" /><ProvChip kind="curado" /><ProvChip kind="calculo" /><ProvChip kind="simulado" />
            <span className="legend-note">Papers: arXiv (atribución en cada paper). Lo simulado es maqueta del motor, aún no conectado.</span>
          </>
        )}
      </footer>
      {devOn && (
        <aside className="devlog" data-devlog={devTick} aria-label="Registro de desarrollo">
          <h2>Qué está haciendo</h2>
          <ol>
            {dev.steps.map((row) => <li key={row.id} className={row.state}>{dev.line(row)}</li>)}
          </ol>
        </aside>
      )}
    </>
  );
}

function CoreList({ papers, states, onOpen, onWant }: { papers: any[]; states: Record<string, any>; onOpen: (id: string) => void; onWant: (id: string) => void }) {
  const ordered = [...papers].sort((a, b) => Number(Boolean(a.retracted)) - Number(Boolean(b.retracted)));
  return (
    <ol className="core-list">
      {ordered.map((p) => {
        const id = paperKey(p);
        const phase = phaseOf(states[id]?.status);
        const reason = states[id]?.reason;
        return (
          <li key={id} className={p.retracted ? "is-sunk" : undefined}>
            <p className={`phase phase-${phase.id}`} data-phase={phase.id}>{phase.label}{phase.id === "fallo" && reason ? ` (${reason})` : ""}</p>
            <h2><button type="button" className="link" onClick={() => onOpen(id)}>{p.title || id}</button></h2>
            <p className="authors">{[p.year, p.citationcount != null ? `${p.citationcount} citas` : null, p.venue].filter((x) => x != null && x !== "").join(" · ")}</p>
            {p.survey && <p className="survey-tag">survey</p>}
            {p.retracted && <p className="retract">retractado</p>}
            {p.abstract ? <p className="core-blurb">{p.abstract}</p> : p.tldr ? <p className="core-blurb"><span className="chip chip-simulado">generado</span> {p.tldr}</p> : <p className="small">Sin abstract en el índice.</p>}
            <button type="button" onClick={() => onWant(id)}>quiero leer este</button>
          </li>
        );
      })}
    </ol>
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
      <div className="view-toggle" role="tablist" aria-label="Vista"><button className={view === "mapa" ? "on" : ""} onClick={() => setView("mapa")}>Mapa</button><button className={view === "tarjetas" ? "on" : ""} onClick={() => setView("tarjetas")}>Tarjetas</button>{!core && <button className={view === "panorama" ? "on" : ""} onClick={() => setView("panorama")}>Panorama</button>}</div>
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
