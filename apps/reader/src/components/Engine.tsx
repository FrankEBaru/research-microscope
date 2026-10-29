"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Paper } from "@/lib/types";
import { Rich } from "@/lib/math";
import { Coverage, ProvChip } from "./Bits";
import PaperView, { plainOf } from "./Paper";
import MapView from "./MapView";
import Panorama, { LiveCoverage } from "./Panorama";
import { modelGrowth, tokenGrowth } from "@/lib/scaling.js";
import { burst, liveEnabled, paperKey, paper as fetchPaper, status as fetchStatus } from "@/lib/backend.js";
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
  const [draft, setDraft] = useState("");
  const [liveQ, setLiveQ] = useState("");
  const [liveOn, setLiveOn] = useState(false);
  const [pending, setPending] = useState(false);
  const [warm, setWarm] = useState(false);
  const [liveResult, setLiveResult] = useState<any>(null);
  const [liveErr, setLiveErr] = useState("");
  const [rowState, setRowState] = useState<Record<string, any>>({});
  const [opened, setOpened] = useState<any>(null);

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
    const k = (e: KeyboardEvent) => { if ((e.key === "c" || e.key === "C") && !e.metaKey && !e.ctrlKey && !e.altKey && !/INPUT|TEXTAREA/.test((e.target as HTMLElement).tagName)) setCompanion((v) => !v); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);

  const go = useCallback((r: Route) => { location.hash = fmt(r); window.scrollTo({ top: 0 }); }, []);
  const liveId = live && route.p && /^\d+$/.test(route.p) ? route.p : "";

  useEffect(() => {
    if (!liveOn || !liveResult) return;
    const ids = (liveResult.papers || []).slice(0, 10).map((p: any) => p.corpusid).filter((id: any) => typeof id === "number");
    if (!ids.length) return;
    let stop = false;
    const tick = async () => {
      try {
        const body = await fetchStatus(ids);
        if (stop) return;
        const map: Record<string, any> = {};
        for (const row of body.papers || []) map[String(row.id)] = row;
        setRowState(map);
        if (ids.every((id: number) => ["done", "abstract_only", "failed"].includes(map[String(id)]?.status))) return;
      } catch (e: any) {
        if (!stop) setLiveErr(String(e.message || e));
      }
      if (!stop) window.setTimeout(tick, 1500);
    };
    tick();
    return () => { stop = true; };
  }, [liveOn, liveResult]);

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
        const st = await fetchStatus([liveId]);
        if (stop) return;
        const row = (st.papers || [])[0] || {};
        const next = `${row.stage || ""}|${row.status || ""}|${row.upgraded_from || ""}`;
        if (next !== sig) {
          sig = next;
          apply(await fetchPaper(liveId));
        }
        if (["done", "abstract_only", "failed"].includes(row.status)) return;
      } catch (e: any) {
        if (!stop) setLiveErr(String(e.message || e));
      }
      if (!stop) window.setTimeout(loop, 2000);
    };
    (async () => {
      try {
        const body = await fetchPaper(liveId);
        if (stop) return;
        sig = signature(body);
        apply(body);
        if (["done", "abstract_only", "failed"].includes(body.status)) return;
      } catch (e: any) {
        if (!stop) setLiveErr(String(e.message || e));
      }
      if (!stop) window.setTimeout(loop, 2000);
    })();
    return () => { stop = true; };
  }, [liveId]);

  const onSearch = async (e: { preventDefault: () => void }) => {
    e.preventDefault();
    const q = draft.trim();
    if (!q || pending) return;
    setLiveQ(q); setLiveOn(true); setLiveErr(""); setLiveResult(null); setRowState({}); setPending(true); setWarm(false);
    const timer = window.setTimeout(() => setWarm(true), 2000);
    try {
      setLiveResult(await burst(q));
      go({});
    } catch (err: any) {
      setLiveErr(String(err.message || err));
    } finally {
      window.clearTimeout(timer); setPending(false); setWarm(false);
    }
  };
  const backToCurated = () => {
    setLiveOn(false); setLiveQ(""); setLiveResult(null); setRowState({}); setOpened(null); setPending(false); setWarm(false); setLiveErr("");
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

  if (err) return <main className="center-msg"><p>{err}</p></main>;
  if (!content || !Object.keys(papers).length) return <main className="center-msg"><p>Cargando…</p></main>;

  const steps = [
    { n: 1, label: "Área", sub: q.text, on: () => go({ q: q.id }) },
    { n: 2, label: "Cluster", sub: cluster?.title, on: cluster ? () => go({ q: q.id, c: cluster.id }) : undefined },
    { n: 3, label: "Paper", sub: paper ? paper.title : undefined, on: undefined },
  ];

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
        <button className="companion-toggle" aria-pressed={companion} onClick={() => setCompanion((v) => !v)} title="Compañero de lectura opcional: ofrece ayuda, nunca interrumpe, no guarda nada (tecla C)">Compañero {companion ? "activado" : "apagado"}</button>
        <span className="proto">prototipo · datos locales</span>
      </header>

      <main key={`${level}-${route.c}-${route.p}`} className="zoom-in">
        {live && (liveOn || liveId) && liveId && opened && (
          <div className="lvl">
            <button type="button" className="link" onClick={backToCurated}>volver a la ráfaga curada</button>
            <PaperView paper={opened.paper} content={content} companion={companion} onHideCompanion={() => setCompanion(false)} remote={opened.remote} />
          </div>
        )}
        {live && (liveOn || liveId) && liveId && !opened && <p className="center-msg">Cargando…</p>}
        {live && liveOn && !liveId && (
          <section className="lvl">
            <button type="button" className="link" onClick={backToCurated}>volver a la ráfaga curada</button>
            <h1 className="question">{liveQ}</h1>
            {pending && warm && <p className="warm">calentando el motor…</p>}
            {liveErr && <p className="fail-reason">{liveErr}</p>}
            {liveResult && <LiveCoverage ids={(liveResult.papers || []).slice(0, 10).map((p: any) => paperKey(p))} states={rowState} />}
            {liveResult && <LiveCircle papers={liveResult.papers || []} edges={liveResult.edges || []} states={rowState} onOpen={(id) => go({ p: id })} />}
          </section>
        )}
        {!(live && (liveOn || liveId)) && level === 1 && <Area q={q} questions={questions} papers={papers} go={go} content={content} />}
        {!(live && (liveOn || liveId)) && level === 2 && cluster && <Cluster q={q} cl={cluster} papers={papers} go={go} />}
        {!(live && (liveOn || liveId)) && level === 3 && paper && <PaperView paper={paper} content={content} focus={route.b} companion={companion} onHideCompanion={() => setCompanion(false)} />}
        {!(live && (liveOn || liveId)) && level === 3 && !paper && <p className="center-msg">Paper no encontrado.</p>}
      </main>

      <footer className="legend">
        <span>Procedencia:</span>
        <ProvChip kind="paper" /><ProvChip kind="curado" /><ProvChip kind="calculo" /><ProvChip kind="simulado" />
        <span className="legend-note">Papers: arXiv (atribución en cada paper). Lo simulado es maqueta del motor, aún no conectado.</span>
      </footer>
    </>
  );
}

/* ---------- Nivel 1: área ---------- */
function Area({ q, questions, papers, go, content }: any) {
  const [view, setView] = useState<"mapa" | "tarjetas" | "panorama">("mapa");
  return (
    <section className="lvl lvl1">
      <p className="eyebrow">Nivel 1 · Área</p>
      <div className="qtabs">{questions.map((x: any) => <button key={x.id} className={x.id === q.id ? "on" : ""} onClick={() => go({ q: x.id })}>{x.text}</button>)}</div>
      <h1 className="question">{q.text}</h1>
      <p className="sub"><ProvChip kind="curado" text="ráfaga de ejemplo curada a mano" /> No es la salida del motor de ráfaga: es el formato que ese motor llenará.</p>
      <div className="view-toggle" role="tablist" aria-label="Vista"><button className={view === "mapa" ? "on" : ""} onClick={() => setView("mapa")}>Mapa</button><button className={view === "tarjetas" ? "on" : ""} onClick={() => setView("tarjetas")}>Tarjetas</button><button className={view === "panorama" ? "on" : ""} onClick={() => setView("panorama")}>Panorama</button></div>
      {view === "mapa" && <MapView q={q} papers={papers} go={go} />}
      {view === "panorama" && <Panorama q={q} papers={papers} content={content} go={go} />}
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
