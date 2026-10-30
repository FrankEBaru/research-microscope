"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Rich } from "@/lib/math";
import { ProvChip } from "./Bits";
import { plainOf } from "./Paper";
import { paperKey } from "@/lib/backend.js";

const W = 1600, H = 1000;
const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));
const short = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
const wrap2 = (s: string, n: number): [string, string] => {
  const w = s.split(" "); let a = "", i = 0;
  while (i < w.length && (a + " " + w[i]).trim().length <= n) a = (a + " " + w[i++]).trim();
  return [a, short(w.slice(i).join(" "), n)];
};
const LENSES = [1, 2, 4, 8];

export default function MapView({ q, papers, go }: any) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 1000, h: 600 });
  const L = q.layout;
  const kFit = Math.min(size.w / W, size.h / H) * 0.96;
  const [view, setView] = useState({ k: 0.6, cx: W / 2, cy: H / 2 });
  const raf = useRef<number>(0);
  const viewRef = useRef(view); viewRef.current = view;
  const z = view.k / kFit;
  const level = z < 1.7 ? 1 : z < 3.6 ? 2 : 3;

  useEffect(() => {
    const el = box.current!; const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el); setSize({ w: el.clientWidth, h: el.clientHeight }); return () => ro.disconnect();
  }, []);
  useEffect(() => { setView({ k: kFit, cx: W / 2, cy: H / 2 }); }, [q.id, kFit]);

  const animateTo = useCallback((t: { k?: number; cx?: number; cy?: number }) => {
    cancelAnimationFrame(raf.current);
    const a = viewRef.current, k1 = clamp(t.k ?? a.k, kFit * 0.9, kFit * 12), cx1 = clamp(t.cx ?? a.cx, 0, W), cy1 = clamp(t.cy ?? a.cy, 0, H);
    const t0 = performance.now(), D = 460;
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - p, 3);
      setView({ k: Math.exp(Math.log(a.k) + (Math.log(k1) - Math.log(a.k)) * e), cx: a.cx + (cx1 - a.cx) * e, cy: a.cy + (cy1 - a.cy) * e });
      if (p < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  }, [kFit]);

  // rueda: zoom hacia el cursor (listener nativo no pasivo)
  useEffect(() => {
    const el = box.current!;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault(); cancelAnimationFrame(raf.current);
      const v = viewRef.current, r = el.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top;
      const k = clamp(v.k * Math.exp(-e.deltaY * 0.0016), kFit * 0.9, kFit * 12);
      const wx = (sx - size.w / 2) / v.k + v.cx, wy = (sy - size.h / 2) / v.k + v.cy;
      setView({ k, cx: clamp(wx - (sx - size.w / 2) / k, 0, W), cy: clamp(wy - (sy - size.h / 2) / k, 0, H) });
    };
    el.addEventListener("wheel", onWheel, { passive: false }); return () => el.removeEventListener("wheel", onWheel);
  }, [size, kFit]);

  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const onDown = (e: React.PointerEvent) => { if ((e.target as HTMLElement).closest("button,.ov,.minimap")) return; cancelAnimationFrame(raf.current); drag.current = { x: e.clientX, y: e.clientY, moved: false }; };
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current; if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y; if (!d.moved && Math.abs(dx) + Math.abs(dy) > 3) { d.moved = true; box.current!.setPointerCapture(e.pointerId); }
    if (!d.moved) return;
    d.x = e.clientX; d.y = e.clientY; const v = viewRef.current;
    setView({ k: v.k, cx: clamp(v.cx - dx / v.k, 0, W), cy: clamp(v.cy - dy / v.k, 0, H) });
  };
  const onUp = () => { setTimeout(() => { drag.current = null; }, 0); };
  const onKey = (e: React.KeyboardEvent) => {
    const v = viewRef.current, s = 90 / v.k;
    if (e.key === "+" || e.key === "=") animateTo({ k: v.k * 1.6 }); else if (e.key === "-") animateTo({ k: v.k / 1.6 });
    else if (e.key === "0") animateTo({ k: kFit, cx: W / 2, cy: H / 2 });
    else if (e.key === "ArrowLeft") animateTo({ cx: v.cx - s }); else if (e.key === "ArrowRight") animateTo({ cx: v.cx + s });
    else if (e.key === "ArrowUp") animateTo({ cy: v.cy - s }); else if (e.key === "ArrowDown") animateTo({ cy: v.cy + s });
    else return; e.preventDefault();
  };

  const sx = (x: number) => (x - view.cx) * view.k + size.w / 2, sy = (y: number) => (y - view.cy) * view.k + size.h / 2;
  const entries = useMemo(() => q.clusters.flatMap((c: any) => c.papers.map((p: any) => ({ ...p, cl: c }))), [q]);
  const near = useMemo(() => {
    let best: any = null, bd = 1e9;
    for (const e of entries) { const [x, y] = L.pos[e.id]; const d = Math.hypot(x - view.cx, y - view.cy); if (d < bd) { bd = d; best = e; } }
    return { e: best, d: bd };
  }, [entries, view.cx, view.cy, L]);
  const active = z >= 2.4 && near.d * view.k < 200 ? near.e : null;
  const cardFor = (id: string) => entries.find((e: any) => e.id === id);
  const lensZ = LENSES.reduce((a, b) => (Math.abs(Math.log(z / b)) < Math.abs(Math.log(z / a)) ? b : a));
  const focus = (id: string) => { const [x, y] = L.pos[id]; animateTo({ k: kFit * 4.2, cx: x, cy: y }); };

  return (
    <div className="platina-wrap">
      <div className="platina" ref={box} tabIndex={0} role="application" aria-label="Mapa explorable: arrastra para mover, rueda o + y − para acercar" onKeyDown={onKey}
        onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
        onDoubleClick={(e) => { const r = box.current!.getBoundingClientRect(); const v = viewRef.current; animateTo({ k: v.k * 2, cx: (e.clientX - r.left - size.w / 2) / v.k + v.cx, cy: (e.clientY - r.top - size.h / 2) / v.k + v.cy }); }}>
        <svg width={size.w} height={size.h} aria-hidden="true">
          <defs>
            <marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="#6d675d" /></marker>
            <pattern id="grid" width="80" height="80" patternUnits="userSpaceOnUse" patternTransform={`translate(${sx(0)} ${sy(0)}) scale(${view.k})`}><path d="M80 0H0V80" fill="none" stroke="#e4ddd0" strokeWidth={1 / view.k} /></pattern>
          </defs>
          <rect width={size.w} height={size.h} fill="url(#grid)" opacity=".6" />
          {Object.entries(L.regions).map(([id, r]: any) => {
            const cl = q.clusters.find((c: any) => c.id === id); const have = cl.papers.filter((p: any) => papers[p.id]?.full).length;
            return (
              <g key={id} className="region" onClick={() => { if (!drag.current?.moved) animateTo({ k: kFit * 2.4, cx: r.cx, cy: r.cy }); }}>
                <circle cx={sx(r.cx)} cy={sy(r.cy)} r={r.r * view.k} className="region-blob" />
                <text x={sx(r.cx)} y={sy(r.cy - r.r) - 10} textAnchor="middle" className="region-title" opacity={z < 2.6 ? 1 : 0.4}>{short(cl.title, z < 1.7 ? 52 : 60)}</text>
                {z < 1.7 && <text x={sx(r.cx)} y={sy(r.cy - r.r) + 8} textAnchor="middle" className="region-sub">{cl.papers.length} {cl.papers.length === 1 ? "paper" : "papers"} · texto completo de {have}</text>}
              </g>
            );
          })}
          {z > 1.1 && L.edges.map((e: any, i: number) => {
            const [x1, y1] = L.pos[e.from], [x2, y2] = L.pos[e.to]; const dx = x2 - x1, dy = y2 - y1, d = Math.hypot(dx, dy) || 1, pad = z >= 1.7 ? 70 : 14;
            const solid = e.kind !== "curado";
            return (
              <line key={i} x1={sx(x1) + (dx / d) * pad} y1={sy(y1) + (dy / d) * pad * 0.55} x2={sx(x2) - (dx / d) * pad} y2={sy(y2) - (dy / d) * pad * 0.55} className={`edge ${solid ? "solid" : "dash"}`} markerEnd="url(#arr)">
                <title>{e.kind === "bibliografia" ? "Confirmada: está en la bibliografía del paper" : e.kind === "abstract" ? `Confirmada en el abstract: «${e.quote}»` : "Relación curada a mano (no verificada en el texto)"}</title>
              </line>
            );
          })}
          {entries.map((e: any) => {
            const p = papers[e.id], [x, y] = L.pos[e.id], px = sx(x), py = sy(y), isA = active?.id === e.id;
            const label = `${p.authors[0]?.split(" ").pop()} ${p.date?.slice(0, 4)}`;
            if (z < 1.7) return (
              <g key={e.id} className="node-dot" onClick={() => { if (!drag.current?.moved) focus(e.id); }}>
                <circle cx={px} cy={py} r={7} className={p.full ? "ring-full" : "ring-abs"} /><text x={px + 12} y={py + 4} className="dot-label">{label}</text>
              </g>);
            const [l1, l2] = wrap2(p.title.replace(/^[^:]+: /, (m: string) => (m.length < 14 ? m : "")), 26);
            return (
              <g key={e.id} className={`node-card ${isA ? "on" : ""}`} transform={`translate(${px - 96} ${py - 31})`} onClick={() => { if (!drag.current?.moved) focus(e.id); }}>
                <rect width="192" height="62" rx="10" className={p.full ? "card-full" : "card-abs"} />
                <text x="12" y="22" className="card-t">{l1}</text><text x="12" y="38" className="card-t">{l2}</text>
                <text x="12" y="54" className="card-s">{label} · {p.full ? "texto completo" : "solo abstract"}</text>
              </g>);
          })}
        </svg>
        <div className="vignette" aria-hidden="true" />
        {!active && <svg className="reticle" width="46" height="46" viewBox="0 0 46 46" aria-hidden="true"><circle cx="23" cy="23" r="16" fill="none" stroke="#1d1b17" strokeOpacity=".5" /><path d="M23 2v10M23 34v10M2 23h10M34 23h10" stroke="#1d1b17" strokeOpacity=".5" /></svg>}

        <div className="hud">
          {["Área", "Cluster", "Paper"].map((n, i) => <span key={n} className={`hud-step ${level === i + 1 ? "on" : ""}`}><b>{i + 1}</b> {n}</span>)}
        </div>
        <div className="lenses" role="group" aria-label="Aumento">
          {LENSES.map((l) => <button key={l} className={lensZ === l ? "on" : ""} onClick={() => animateTo({ k: kFit * l })}>×{l}</button>)}
        </div>

        <div className="minimap" aria-label="Minimapa" onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); animateTo({ cx: ((e.clientX - r.left) / r.width) * W, cy: ((e.clientY - r.top) / r.height) * H }); }}>
          <svg viewBox={`0 0 ${W} ${H}`}>
            {Object.values(L.regions).map((r: any, i) => <circle key={i} cx={r.cx} cy={r.cy} r={r.r} className="mm-region" />)}
            {entries.map((e: any) => <circle key={e.id} cx={L.pos[e.id][0]} cy={L.pos[e.id][1]} r="16" className={papers[e.id].full ? "mm-full" : "mm-abs"} />)}
            <rect x={view.cx - size.w / view.k / 2} y={view.cy - size.h / view.k / 2} width={size.w / view.k} height={size.h / view.k} className="mm-view" vectorEffect="non-scaling-stroke" />
          </svg>
        </div>

        {level === 3 && active && <OneMinute e={active} p={papers[active.id]} q={q} go={go} />}
      </div>
      <p className="map-legend">
        <span className="lg lg-full" /> texto completo · <span className="lg lg-abs" /> solo abstract · <span className="lg-line solid" /> relación confirmada en el texto (bibliografía o abstract) · <span className="lg-line dash" /> relación curada a mano ·{" "}
        <ProvChip kind="curado" text="posiciones ilustrativas" /> en el motor real vendrían de una proyección de SPECTER2. Arrastra para mover · rueda, +/− o los lentes para acercar · doble clic acerca.
      </p>
    </div>
  );
}

export function LiveCircle({ papers, edges, states, onOpen }: { papers: any[]; edges: any[]; states: Record<string, any>; onOpen: (id: string) => void }) {
  const n = Math.max(papers.length, 1);
  const cx = 320, cy = 200, r = 150;
  const nodes = papers.map((p, i) => {
    const ang = -Math.PI / 2 + (2 * Math.PI * i) / n;
    const id = paperKey(p);
    return { id, p, x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang) };
  });
  const at: Record<string, (typeof nodes)[number]> = Object.fromEntries(nodes.map((node) => [node.id, node]));
  const queued = (id: string) => {
    const st = states[id];
    return !st || st.status === "missing" || st.status === "queued";
  };
  return (
    <div className="live-map">
      <svg viewBox="0 0 640 420" width="100%" role="img" aria-label="Ráfaga en vivo">
        {(edges || []).map((e: any, i: number) => {
          const a = at[String(e.citing)], b = at[String(e.cited)];
          if (!a || !b) return null;
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="edge solid" />;
        })}
        {nodes.map((node) => (
          <g key={node.id} className="node-dot" onClick={() => onOpen(node.id)}>
            <circle cx={node.x} cy={node.y} r={11} className={queued(node.id) ? "ring-queue" : "ring-full"} />
            <text x={node.x} y={node.y + 26} textAnchor="middle" className="dot-label">{queued(node.id) ? "en cola" : short(node.p.title || node.id, 32)}</text>
          </g>
        ))}
      </svg>
      <p className="map-legend">aristas = citas (Semantic Scholar); el orden en el círculo es el ranking, no un mapa semántico</p>
      <ol className="live-rows">
        {papers.map((p) => {
          const id = paperKey(p);
          const st = states[id];
          return (
            <li key={id}>
              <button type="button" onClick={() => onOpen(id)}>{p.title}</button>
              <span className="authors">{[p.year, p.venue, p.citationcount].filter((x) => x != null && x !== "").join(" · ")}{queued(id) ? " · en cola" : ""}{st?.status === "failed" ? ` · ${st.reason || ""}` : ""}</span>
            </li>
          );
        })}
      </ol>
      <p>Datos de papers y citas: Semantic Scholar</p>
    </div>
  );
}

function OneMinute({ e, p, q, go }: any) {
  const fig = e.figure && p.blocks.find((b: any) => b.label === e.figure);
  return (
    <aside className="ov" aria-label="Vista de un minuto">
      <div className="chips"><ProvChip kind="paper" text={`arXiv:${p.arxivId}`} />{!p.full && <ProvChip kind="curado" text="solo abstract" />}</div>
      <h3>{p.title}</h3>
      <p className="authors">{p.authors.slice(0, 3).join(", ")}{p.authors.length > 3 ? " et al." : ""} · {p.date?.slice(0, 4)}</p>
      <blockquote><span className="qlab">Aporte, en palabras del abstract</span>«<Rich text={e.contribution.quote} />»</blockquote>
      <button className="primary" onClick={() => go({ q: q.id, c: e.cl.id, p: p.arxivId, b: e.contribution.anchor.blockId })}>Abrir el paper →</button>
      {fig && <figure className="thumb"><img src={fig.images[0]} alt={plainOf(fig.caption)} /><figcaption><b>Figura 1 del paper</b></figcaption></figure>}
      {e.pending && <blockquote><span className="qlab">Pendiente declarado por el paper</span>«<Rich text={e.pending.quote} />»</blockquote>}
    </aside>
  );
}
