"use client";
import { useEffect, useMemo, useState } from "react";
import { ProvChip } from "./Bits";
import { paperKey } from "@/lib/backend.js";
import { phaseOf } from "@/lib/qcache.js";
import { clusterColor, layoutOf, mapCaption, pointRadius, statusLine } from "@/lib/layout.js";
import { LENSES, usePlatina } from "./usePlatina";

const short = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
const CHAR_W = 6.4;

function labelGeom(px: number, py: number, r: number, raw: string, w: number, h: number, others: { x: number; y: number }[]) {
  if (px < -36 || px > w + 80 || py < 0 || py > h) return null;
  const gap = r + 8;
  const widthOf = (s: string) => s.length * CHAR_W + 10;
  const rightRoom = w - 16 - (px + gap);
  const leftRoom = px - gap - 16;
  const flip = rightRoom < widthOf(raw) && leftRoom > rightRoom;
  let anchor: "start" | "end" = flip ? "end" : "start";
  let x = flip ? -gap : gap;
  let text = short(raw, Math.max(14, Math.floor(Math.max(flip ? leftRoom : rightRoom, 48) / CHAR_W)));
  if (anchor === "end") {
    if (px + x > w - 12) x -= px + x - (w - 12);
    if (px + x - widthOf(text) < 12) text = short(text, Math.max(14, Math.floor((px + x - 12) / CHAR_W)));
  } else if (px + x + widthOf(text) > w - 12) {
    anchor = "end";
    x = Math.min(-gap, w - 12 - px);
    text = short(raw, Math.max(14, Math.floor((px + x - 12) / CHAR_W)));
  }
  const dir = anchor === "end" ? -1 : 1;
  const far = px + x + dir * text.length * CHAR_W;
  const hits = others.some((other) => {
    if (Math.abs(other.y - py) > 18) return false;
    const lo = Math.min(px + dir * r, far);
    const hi = Math.max(px + dir * r, far);
    return other.x > lo && other.x < hi;
  });
  return { x, y: hits ? -(r + 10) : 4, anchor, text };
}

function reducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function ease(t: number) {
  const p = Math.min(1, Math.max(0, t));
  return 1 - Math.pow(1 - p, 3);
}

export default function LiveMap({ papers, edges, layout, states, onOpen, onWant }: {
  papers: any[];
  edges: any[];
  layout: any;
  states: Record<string, any>;
  onOpen: (id: string) => void;
  onWant: (id: string) => void;
}) {
  const model = useMemo(() => layoutOf({ papers, edges, layout }), [papers, edges, layout]);
  const ids = papers.map((p) => paperKey(p)).join(",");
  const plat = usePlatina(ids);
  const { box, size, view, kFit, z, sx, sy, animateTo, lensZ, drag, onDown, onMove, onUp, onKey } = plat;
  const byId = useMemo(() => {
    const map = new Map<string, any>();
    papers.forEach((paper, rank) => map.set(paperKey(paper), { paper, rank }));
    return map;
  }, [papers]);
  const targets = model.points || [];
  const [shown, setShown] = useState<{ x: number; y: number; s: number }[]>(() => targets.map(() => ({ x: 800, y: 500, s: 0 })));
  const [settled, setSettled] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const caption = mapCaption(model);

  useEffect(() => {
    const reduce = reducedMotion();
    const from = targets.map(() => ({ x: 800, y: 500 }));
    if (reduce || targets.length === 0) {
      setShown(targets.map((p: any) => ({ x: p.x, y: p.y, s: 1 })));
      setSettled(true);
      return;
    }
    setSettled(false);
    let raf = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const elapsed = now - t0;
      let done = true;
      const next = targets.map((p: any, i: number) => {
        const delay = i * 46;
        const t = Math.min(1, Math.max(0, (elapsed - delay) / 900));
        if (t < 1) done = false;
        const e = ease(t);
        return {
          x: from[i].x + (p.x - from[i].x) * e,
          y: from[i].y + (p.y - from[i].y) * e,
          s: Math.min(1, Math.max(0, (elapsed - delay) / 260)),
        };
      });
      setShown(next);
      if (!done) raf = requestAnimationFrame(step);
      else setSettled(true);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [model, targets]);

  const at = (cid: number) => {
    const i = targets.findIndex((p: any) => p.corpusid === cid);
    if (i < 0) return null;
    return shown[i] || { x: targets[i].x, y: targets[i].y, s: 1 };
  };
  const citePairs = new Set((model.links || []).map((e: any) => `${Math.min(e.citing, e.cited)}:${Math.max(e.citing, e.cited)}`));
  const years = model.method === "year-citation" ? yearTicks(papers, targets) : [];
  const line = statusLine(papers, states);
  const hoverId = hover;
  const hoverPaper = hoverId ? byId.get(hoverId) : null;
  const hoverPoint = hoverPaper ? targets.find((p: any) => String(p.corpusid) === hoverId) : null;
  const hoverShown = hoverPoint ? shown[targets.indexOf(hoverPoint)] : null;

  let tipStyle: { left: number; top: number } | null = null;
  if (hoverShown && hoverPoint) {
    const r = pointRadius(hoverPoint.rank, targets.length) + 14;
    let left = sx(hoverShown.x) + r;
    let top = sy(hoverShown.y) - 24;
    if (left + 300 > size.w) left = Math.max(8, sx(hoverShown.x) - 300 - r);
    if (top + 210 > size.h) top = Math.max(8, size.h - 218);
    if (top < 8) top = 8;
    tipStyle = { left, top };
  }

  return (
    <div className="platina-wrap" data-live-map data-method={model.method} data-settled={settled ? "1" : "0"}>
      <div
        className="platina"
        ref={box}
        tabIndex={0}
        role="application"
        aria-label="Mapa de la ráfaga: arrastra para mover, rueda o + y − para acercar. Cada punto es un paper."
        onKeyDown={onKey}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onDoubleClick={(e) => {
          const r = box.current!.getBoundingClientRect();
          animateTo({
            k: view.k * 2,
            cx: (e.clientX - r.left - size.w / 2) / view.k + view.cx,
            cy: (e.clientY - r.top - size.h / 2) / view.k + view.cy,
          });
        }}
      >
        <svg width={size.w} height={size.h} aria-hidden="true">
          <defs>
            <marker id="live-arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="#6d675d" /></marker>
            <pattern id="live-grid" width="80" height="80" patternUnits="userSpaceOnUse" patternTransform={`translate(${sx(0)} ${sy(0)}) scale(${view.k})`}>
              <path d="M80 0H0V80" fill="none" stroke="#e4ddd0" strokeWidth={1 / view.k} />
            </pattern>
          </defs>
          <rect width={size.w} height={size.h} fill="url(#live-grid)" opacity=".55" />
          {years.some((tick) => tick.label !== "sin año") && (
            <YearAxis years={years} sx={sx} sy={sy} size={size} />
          )}
          {(model.links || []).map((e: any, i: number) => {
            const a = at(e.citing);
            const b = at(e.cited);
            if (!a || !b || a.s < 0.2 || b.s < 0.2) return null;
            return <line key={`c${i}`} x1={sx(a.x)} y1={sy(a.y)} x2={sx(b.x)} y2={sy(b.y)} className="edge solid" markerEnd="url(#live-arr)" strokeOpacity={0.55} />;
          })}
          {(model.similarity || []).map((e: any, i: number) => {
            const key = `${Math.min(e.a, e.b)}:${Math.max(e.a, e.b)}`;
            if (citePairs.has(key)) return null;
            const a = at(e.a);
            const b = at(e.b);
            if (!a || !b) return null;
            return <line key={`s${i}`} x1={sx(a.x)} y1={sy(a.y)} x2={sx(b.x)} y2={sy(b.y)} className="edge dash" strokeOpacity={0.8} />;
          })}
          {targets.map((point: any, i: number) => {
            const id = String(point.corpusid);
            const meta = byId.get(id);
            if (!meta) return null;
            const here = shown[i] || { x: point.x, y: point.y, s: 1 };
            const phase = phaseOf(states[id]?.status);
            const r = pointRadius(point.rank, targets.length) * Math.max(here.s, 0.001);
            const label = z >= 1.55 || point.rank === 0 ? (meta.paper.title || id) : "";
            return (
              <g
                key={id}
                className="node-dot"
                transform={`translate(${sx(here.x)} ${sy(here.y)})`}
                onPointerEnter={() => setHover(id)}
                onFocus={() => setHover(id)}
                onClick={(e) => { e.stopPropagation(); if (!drag.current?.moved) onOpen(id); }}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); onOpen(id); } }}
                tabIndex={0}
                role="button"
                aria-label={`${meta.paper.title || id}. ${phase.label}`}
              >
                <circle r={r + 3} fill={clusterColor(point.cluster)} opacity={phase.id === "fallo" ? 0.35 : 0.95} />
                <circle
                  r={r + 5}
                  fill="none"
                  stroke={phase.id === "fallo" ? "#8d2a2a" : phase.id === "listo" ? "#3d5a47" : phase.id === "preparando" ? "#27476b" : "#fffdf8"}
                  strokeWidth={phase.id === "preparando" ? 2.4 : 1.6}
                  className={phase.id === "preparando" ? "ring-prep" : undefined}
                />
                {phase.id === "fallo" && <text textAnchor="middle" y="4" className="dot-x">×</text>}
                {label && here.s > 0.65 && (() => {
                  const px = sx(here.x);
                  const py = sy(here.y);
                  const others = targets.map((other: any, j: number) => ({ x: sx((shown[j] || other).x), y: sy((shown[j] || other).y) }));
                  const place = labelGeom(px, py, r, label, size.w, size.h, others);
                  if (!place) return null;
                  return <text x={place.x} y={place.y} textAnchor={place.anchor} className="dot-label">{place.text}</text>;
                })()}
              </g>
            );
          })}
        </svg>
        <div className="lenses" role="group" aria-label="Aumento">
          {LENSES.map((l) => <button key={l} type="button" className={lensZ === l ? "on" : ""} onClick={() => animateTo({ k: kFit * l })}>×{l}</button>)}
        </div>
        <div className="minimap live-minimap" aria-label="Minimapa" onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          animateTo({ cx: ((e.clientX - r.left) / r.width) * 1600, cy: ((e.clientY - r.top) / r.height) * 1000 });
        }}>
          <svg viewBox="0 0 1600 1000">
            {(model.links || []).map((e: any, i: number) => {
              const a = targets.find((p: any) => p.corpusid === e.citing);
              const b = targets.find((p: any) => p.corpusid === e.cited);
              if (!a || !b) return null;
              return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#6d675d" strokeWidth="8" />;
            })}
            {targets.map((p: any) => <circle key={p.corpusid} cx={p.x} cy={p.y} r="18" fill={clusterColor(p.cluster)} />)}
            <rect x={view.cx - size.w / view.k / 2} y={view.cy - size.h / view.k / 2} width={size.w / view.k} height={size.h / view.k} className="mm-view" vectorEffect="non-scaling-stroke" />
          </svg>
        </div>
        {line && <p className="map-status" role="status">{line}</p>}
        {hoverPaper && tipStyle && (
          <aside className="map-tip" style={tipStyle} onPointerDown={(e) => e.stopPropagation()}>
            <p className={`phase phase-${phaseOf(states[hoverId!]?.status).id}`}>
              {phaseOf(states[hoverId!]?.status).label}
              {states[hoverId!]?.status === "abstract_only" ? " · solo abstract" : ""}
              {phaseOf(states[hoverId!]?.status).id === "fallo" && states[hoverId!]?.reason ? ` (${states[hoverId!].reason})` : ""}
            </p>
            <h3>{hoverPaper.paper.title || hoverId}</h3>
            <p className="authors">{[hoverPaper.paper.year, hoverPaper.paper.citationcount != null ? `${hoverPaper.paper.citationcount} citas` : null].filter((x) => x != null && x !== "").join(" · ") || "sin año ni citas en el índice"}</p>
            {hoverPaper.paper.tldr || hoverPaper.paper.abstract
              ? <p className="tldr">{short(hoverPaper.paper.tldr || hoverPaper.paper.abstract, 280)}</p>
              : <p className="authors">Sin TLDR en esta respuesta.</p>}
            <div className="map-actions">
              <button type="button" className="primary" onClick={() => onOpen(hoverId!)}>Abrir</button>
              <button type="button" className="link" onClick={() => onWant(hoverId!)}>quiero leer este</button>
            </div>
          </aside>
        )}
      </div>
      <p className="map-legend">
        <ProvChip kind={caption.positionKind as any} text={caption.position} title={caption.positionTitle} />
        {caption.edges && <ProvChip kind="paper" text={caption.edges} title="Arista solo si Semantic Scholar trae esa cita entre dos papers de esta ráfaga." />}
        {caption.similar && <ProvChip kind="calculo" text={caption.similar} title="El vecino de mayor coseno SPECTER2, si pasa el umbral. No es una cita." />}
        {" "}Tamaño: puesto en la ráfaga. Anillo: encontrado, preparando, listo o falló.
        {caption.note ? ` ${caption.note}` : ""}
      </p>
    </div>
  );
}

function YearAxis({ years, sx, sy, size }: { years: { label: string; x: number }[]; sx: (x: number) => number; sy: (y: number) => number; size: { w: number; h: number } }) {
  const numbered = years.filter((tick) => tick.label !== "sin año");
  const first = numbered[0];
  const last = numbered[numbered.length - 1];
  const drawn: { label: string; x: number; y: number }[] = [];
  for (const tick of years) {
    let x = sx(tick.x);
    const y = sy(968);
    const prev = drawn[drawn.length - 1];
    const miniW = size.w < 760 ? 130 : 190;
    const miniRight = 12 + miniW;
    const half = Math.max(16, tick.label.length * 4.2);
    const inMiniBand = y > size.h - 12 - miniW * 10 / 16 - 10;
    if (inMiniBand && x - half < miniRight + 6) {
      if (tick.label !== first?.label && tick.label !== last?.label && tick.label !== "sin año") continue;
      x = miniRight + 8 + half;
    }
    const keep = !prev || Math.abs(x - prev.x) >= 46 || tick.label === first?.label || tick.label === last?.label || tick.label === "sin año";
    if (!keep) continue;
    if (prev && Math.abs(x - prev.x) < 46 && tick.label !== first?.label && tick.label !== "sin año") drawn.pop();
    drawn.push({ label: tick.label, x, y });
  }
  if (!first) return null;
  return (
    <g className="year-axis">
      <line x1={sx(first.x)} y1={sy(940)} x2={sx(last.x)} y2={sy(940)} stroke="#d3cabb" strokeWidth="1" />
      {drawn.map((tick) => (
        <text key={tick.label} x={tick.x} y={tick.y} textAnchor="middle" className="year-label">{tick.label}</text>
      ))}
    </g>
  );
}

function yearTicks(papers: any[], points: any[]) {
  const at = new Map<number, number>(points.map((p) => [p.corpusid, p.x]));
  const ticks = new Map<string, number>();
  for (const paper of papers) {
    const x = at.get(paper.corpusid);
    if (x == null) continue;
    if (paper.year == null) ticks.set("sin año", x);
    else ticks.set(String(paper.year), x);
  }
  return [...ticks.entries()]
    .map(([label, x]) => ({ label, x }))
    .sort((a, b) => a.x - b.x);
}
