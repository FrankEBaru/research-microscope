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
import { burst, explain, liveEnabled, paperKey, paper as fetchPaper, prepare, settled, status as fetchStatus, subtopics as fetchSubtopics, warm } from "@/lib/backend.js";
import { coreMode } from "@/lib/features.js";
import { normalizeQuestion, phaseOf, readOverflow, recallQuestion, rememberQuestion, writeOverflow } from "@/lib/qcache.js";
import { bindDevLog, createDevLog } from "@/lib/devlog.js";
import { LiveCircle } from "./MapView";

type Route = { q?: string; c?: string; p?: string; b?: string };
const parse = (h: string): Route => {
  const parts = h.replace(/^#\/?/, "").split("/").filter(Boolean);
  const r: any = {};
  for (let i = 0; i + 1 < parts.length; i += 2) r[parts[i]] = decodeURIComponent(parts[i + 1]);
  return r;
};
const fmt = (r: Route) => "#/" + (["q", "c", "p", "b"] as const).filter((k) => r[k]).map((k) => `${k}/${encodeURIComponent(r[k]!)}`).join("/");

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
    if (!live) { setEngine("listo"); return; }
    let stop = false;
    const burstStep = note("motor de ráfaga", "GET /warm");
    const readerStep = note("motor de lectura", "GET /warm");
    warm("burst").then(
      () => { if (!stop) done(burstStep, "ok", "listo"); },
      (err: any) => { if (!stop) done(burstStep, "error", explain(err)); },
    );
    warm("reader").then(
      () => { if (!stop) { done(readerStep, "ok", "listo"); setEngine("listo"); } },
      (err: any) => { if (!stop) { done(readerStep, "error", explain(err)); setEngine("listo"); } },
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
    if (!liveId) { setOpened(null); return; }
    let stop = false;
    let sig = "";
    const apply = (body: any) => {
      const doc = body.paper || {};
      const meta = body.meta || {};
      setOpened({
        paper: {
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
        },
        remote: {
          status: body.status,
          stage: doc.stage || meta.stage,
          reason: meta.reason,
          source: doc.source || meta.source,
        },
      });
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
    return () => { stop = true; };
  }, [liveId, liveQ]);

  const onSearch = async (e: { preventDefault: () => void }) => {
    e.preventDefault();
    const q = draft.trim();
    if (!q || pending) return;
    setLiveQ(q); setLiveOn(true); setLiveErr(""); setImpatient(false); setForced(false); setTopics(null);
    let cached: any = null;
    try { cached = recallQuestion(localStorage, q); } catch { cached = null; }
    if (cached?.payload?.result) {
      const step = note("pregunta", normalizeQuestion(q));
      setLiveResult(cached.payload.result);
      setRowState(cached.payload.states || {});
      setPending(false);
      done(step, "ok", "caché del navegador");
      go({});
      return;
    }
    setLiveResult(null); setRowState({}); setPending(true);
    const step = note("ráfaga", q);
    try {
      const body = await burst(q);
      setLiveResult(body);
      const bits = body?.seconds ? Object.entries(body.seconds).map(([k, v]) => `${k} ${v}s`).join(", ") : "";
      done(step, "ok", body?.cached ? `caché del servidor${bits ? ` — ${bits}` : ""}` : bits);
      go({});
    } catch (err: any) {
      setLiveErr(explain(err));
      done(step, "error", explain(err));
    } finally {
      setPending(false);
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
        <nav className="scope" aria-label="Nivel de zoom">
          {steps.map((s, i) => (
            <button key={s.n} className={`step ${level === s.n ? "on" : ""} ${level > s.n ? "past" : ""}`} disabled={!s.on || level === s.n} onClick={s.on} title={s.sub || ""}>
              <span className="dot">{s.n}</span><span className="lbl">{s.label}</span>
            </button>
          ))}
        </nav>
        {live && (
          <form className="live-search" onSubmit={onSearch}>
            <input aria-label="Pregunta" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Pregunta" />
            <button type="submit">Buscar</button>
          </form>
        )}
        {!core && <button className="companion-toggle" aria-pressed={companion} onClick={() => setCompanion((v) => !v)} title="Compañero de lectura opcional: ofrece ayuda, nunca interrumpe, no guarda nada (tecla C)">Compañero {companion ? "activado" : "apagado"}</button>}
        <span className="proto">prototipo · datos locales</span>
      </header>

      <main key={`${level}-${route.c}-${route.p}`} className="zoom-in">
        {live && (liveOn || liveId) && liveId && opened && (
          <div className="lvl">
            {!core && <button type="button" className="link" onClick={backToCurated}>volver a la ráfaga curada</button>}
            {core && <button type="button" className="link" onClick={backToCurated}>volver a la lista</button>}
            <PaperView paper={opened.paper} content={content || {}} focus={route.b} companion={core ? false : companion} onHideCompanion={() => setCompanion(false)} remote={opened.remote} showInstrument={!core} showCrops={!core} />
          </div>
        )}
        {live && (liveOn || liveId) && liveId && !opened && (
          <div className="lvl">
            {!core && <button type="button" className="link" onClick={backToCurated}>volver a la ráfaga curada</button>}
            {core && <button type="button" className="link" onClick={backToCurated}>volver a la lista</button>}
            <p className="center-msg">{liveErr ? "No se pudo cargar el paper (se sigue intentando)." : "Cargando…"}</p>
            {liveErr && <p className="fail-reason" role="alert">{liveErr}</p>}
          </div>
        )}
        {live && core && !liveOn && !liveId && (
          <section className="lvl">
            <h1 className="question">Una pregunta</h1>
            <p className="sub">Título, año, citas y TLDR salen del índice. El texto completo de los 10 primeros se prepara después, en segundo plano.</p>
            {engine === "preparando" && <p className="warm" role="status">preparando el motor…</p>}
          </section>
        )}
        {live && liveOn && !liveId && (
          <section className="lvl">
            {!core && <button type="button" className="link" onClick={backToCurated}>volver a la ráfaga curada</button>}
            <h1 className="question">{liveQ}</h1>
            {!core && topics && <p className="sub" data-subtopics>{topics.length ? <>Subtemas: {topics.join(" · ")}</> : "Esta pregunta no separó subtemas."}</p>}
            {engine === "preparando" && !liveResult && <p className="warm" role="status">preparando el motor…</p>}
            {pending && !liveResult && engine !== "preparando" && <p className="warm" role="status">buscando…</p>}
            {liveErr && <p className="fail-reason">{liveErr}</p>}
            {core && liveResult && (
              <>
                <CoreList papers={liveResult.papers || []} states={rowState} onOpen={(id: string) => go({ p: id })} onWant={wantThis} />
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
        {!(live && core) && !(live && (liveOn || liveId)) && level === 3 && paper && <PaperView paper={paper} content={content} focus={route.b} companion={core ? false : companion} onHideCompanion={() => setCompanion(false)} showInstrument={!core} showCrops={!core} />}
        {!(live && (liveOn || liveId)) && level === 3 && !paper && <p className="center-msg">Paper no encontrado.</p>}
      </main>

      <footer className="legend">
        <span>Procedencia:</span>
        <ProvChip kind="paper" /><ProvChip kind="curado" /><ProvChip kind="calculo" /><ProvChip kind="simulado" />
        <span className="legend-note">Papers: arXiv (atribución en cada paper). Lo simulado es maqueta del motor, aún no conectado.</span>
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
  return (
    <ol className="core-list">
      {papers.map((p) => {
        const id = paperKey(p);
        const phase = phaseOf(states[id]?.status);
        const reason = states[id]?.reason;
        const blurb = p.tldr || p.abstract || "";
        return (
          <li key={id}>
            <p className={`phase phase-${phase.id}`} data-phase={phase.id}>{phase.label}{phase.id === "fallo" && reason ? ` (${reason})` : ""}</p>
            <h2><button type="button" className="link" onClick={() => onOpen(id)}>{p.title || id}</button></h2>
            <p className="authors">{[p.year, p.citationcount != null ? `${p.citationcount} citas` : null, p.venue].filter((x) => x != null && x !== "").join(" · ")}</p>
            {blurb ? <p className="core-blurb">{blurb}</p> : null}
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
                  <figure className="thumb"><img src={fig.images[0]} alt={plainOf(fig.caption)} /><figcaption><b>Figura 1 del paper</b> · {plainOf(fig.caption)}</figcaption></figure>
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
