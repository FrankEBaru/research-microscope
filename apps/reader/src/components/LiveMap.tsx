"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { ProvChip } from "./Bits";
import { mapLayout, paperKey } from "@/lib/backend.js";
import { phaseOf } from "@/lib/qcache.js";
import { farGroupIds, layoutOf, mapCaption, nodeLabel, statusLine } from "@/lib/layout.js";
import { LENSES, usePlatina, type Frame } from "./usePlatina";

// Franklin (1 nov): las lentes no ayudan a leer el mapa. El código sigue; la cámara se mueve con rueda y arrastre.
const showLenses = false;
const CLUSTER_HEX = ["#27476b", "#3d5a47", "#8a5a2b", "#5c4d7a", "#3e6b66", "#6d5a4a"];
function clusterHex(id: any) {
  const n = Number(id) || 0;
  return CLUSTER_HEX[((n % CLUSTER_HEX.length) + CLUSTER_HEX.length) % CLUSTER_HEX.length];
}

const short = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
const fitWords = (s: string, n: number) => {
  if (s.length <= n) return s;
  const cut = s.slice(0, Math.max(1, n)).replace(/\s+\S*$/, "").trim();
  const base = cut.length >= 4 ? cut : s.slice(0, Math.max(1, n - 1)).trimEnd();
  return base + "…";
};
const CHAR_W = 6.4;

function namesOf(paper: any): string[] {
  return (Array.isArray(paper?.authors) ? paper.authors : [])
    .map((author: any) => (typeof author === "string" ? author : author?.name))
    .filter(Boolean);
}

function shortName(paper: any) {
  return nodeLabel(paper);
}

function overlaps(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }) {
  return a.x < b.x + b.w + 14 && a.x + a.w + 14 > b.x && a.y < b.y + b.h + 10 && a.y + a.h + 10 > b.y;
}

function fitTitle(title: string, chord: number) {
  for (const size of [17, 15, 13, 12]) {
    if (title.length * size * 0.54 <= chord) return { size, text: title };
  }
  return { size: 12, text: fitWords(title, Math.max(8, Math.floor(chord / 6.5))) };
}

function labelChoices(px: number, py: number, r: number, raw: string, w: number, h: number) {
  if (px < 8 || px > w - 8 || py < 12 || py > h - 8) return [];
  const text = short(raw, 36);
  const tw = text.length * CHAR_W + 6;
  const out: { x: number; y: number; anchor: "start" | "end"; text: string; box: { x: number; y: number; w: number; h: number } }[] = [];
  const add = (x: number, yOff: number, anchor: "start" | "end", x0: number) => {
    const y = py + yOff;
    if (x0 < 6 || x0 + tw > w - 6 || y < 14 || y > h - 4) return;
    out.push({ x, y: yOff, anchor, text, box: { x: x0, y: y - 12, w: tw, h: 15 } });
  };
  add(-tw / 2, -(r + 13), "start", px - tw / 2);
  const gap = r + 7;
  add(gap, 4, "start", px + gap);
  add(-gap, 4, "end", px - gap - tw);
  return out;
}

function reducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function ease(t: number) {
  const p = Math.min(1, Math.max(0, t));
  return 1 - Math.pow(1 - p, 3);
}

function fullText(paper: any, state: any) {
  if (paper?.full || state?.text) return true;
  if (state?.status === "done") return true;
  if (state?.source === "latex" || state?.source === "ocr") return true;
  return state?.stages?.sections === "done";
}

function sceneKey(frame: Frame | null) {
  if (!frame) return "0";
  return [frame.minX, frame.minY, frame.maxX, frame.maxY].map((n) => Math.round(n)).join(",");
}

function contentFrame(groups: any[], points: any[]): Frame | null {
  if (groups.length) {
    return {
      minX: Math.min(...groups.map((g) => g.cx - g.r)) - 20,
      maxX: Math.max(...groups.map((g) => g.cx + g.r)) + 20,
      minY: Math.min(...groups.map((g) => g.cy - g.r * 1.62)),
      maxY: Math.max(...groups.map((g) => g.cy + g.r)) + 26,
    };
  }
  if (!points.length) return null;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  return { minX: Math.min(...xs) - 48, maxX: Math.max(...xs) + 48, minY: Math.min(...ys) - 48, maxY: Math.max(...ys) + 48 };
}

function reflowNarrow(groups: any[], points: any[]) {
  const cols = Math.ceil(groups.length / 2);
  const gap = 64;
  let y = 0;
  const rows: { id: number; x: number; y: number }[][] = [];
  const widths: number[] = [];
  for (let i = 0; i < groups.length; i += cols) {
    const row = groups.slice(i, i + cols);
    const rh = Math.max(...row.map((g) => g.r));
    y += rh * 0.7 + rh;
    let x = 0;
    const items: { id: number; x: number; y: number }[] = [];
    for (const g of row) {
      x += g.r;
      items.push({ id: g.id, x, y });
      x += g.r + gap;
    }
    rows.push(items);
    widths.push(x - gap);
    y += rh + 12;
  }
  const maxW = Math.max(...widths, 1);
  const at = new Map<number, { x: number; y: number }>();
  rows.forEach((items, i) => {
    const shift = (maxW - widths[i]) / 2;
    items.forEach((item) => at.set(item.id, { x: item.x + shift, y: item.y }));
  });
  const nextGroups = groups.map((g) => {
    const pos = at.get(g.id);
    return pos ? { ...g, cx: pos.x, cy: pos.y } : g;
  });
  const nextPoints = points.map((p) => {
    const pos = at.get(p.cluster);
    const from = groups.find((g) => g.id === p.cluster);
    if (!pos || !from) return p;
    return { ...p, x: p.x + pos.x - from.cx, y: p.y + pos.y - from.cy };
  });
  return { groups: nextGroups, points: nextPoints };
}

function staggerWide(groups: any[], points: any[]) {
  if (groups.length < 3) return { groups, points };
  const drop = Math.min(...groups.map((g) => g.r)) * 0.85;
  const nextGroups = groups.map((g, i) => (i % 2 ? { ...g, cy: g.cy + drop } : g));
  const moved = new Map(groups.map((g, i) => [g.id, i % 2 ? drop : 0]));
  const nextPoints = points.map((p) => {
    const dy = moved.get(p.cluster) || 0;
    return dy ? { ...p, y: p.y + dy } : p;
  });
  return { groups: nextGroups, points: nextPoints };
}

function placeScene(model: any, w: number) {
  const groups = (model.groups || []).filter((g: any) => Number.isFinite(g.cx) && Number.isFinite(g.r) && g.r > 0);
  const points = (model.points || []).map((p: any) => ({ ...p }));
  const knn = model.method === "specter2-knn";
  const narrow = w > 0 && w < 760 && groups.length >= 4 && knn;
  const placed = narrow ? reflowNarrow(groups, points) : knn ? staggerWide(groups, points) : { groups, points };
  const frame = contentFrame(placed.groups, placed.points);
  return { ...placed, frame, frameKey: `${sceneKey(frame)}:${narrow ? "n" : "w"}` };
}

export default function LiveMap({ papers, edges, layout, states, onOpen, onWant, query, onLayout }: {
  papers: any[];
  edges: any[];
  layout: any;
  states: Record<string, any>;
  onOpen: (id: string) => void;
  onWant: (id: string) => void;
  query?: string;
  onLayout?: (layout: any) => void;
}) {
  const model = useMemo(() => layoutOf({ papers, edges, layout }), [papers, edges, layout]);
  const ids = papers.map((p) => paperKey(p)).join(",");
  const [frame, setFrame] = useState<Frame | null>(null);
  const frameHeld = useRef("");
  const plat = usePlatina(ids, frame);
  const { box, size, view, kFit, sx, sy, animateTo, lensZ, drag, onDown, onMove, onUp, onKey } = plat;
  const scene = useMemo(() => placeScene(model, size.w), [model, size.w]);
  if (frameHeld.current !== scene.frameKey) {
    frameHeld.current = scene.frameKey;
    setFrame(scene.frame);
  }
  const byId = useMemo(() => {
    const map = new Map<string, any>();
    papers.forEach((paper, rank) => map.set(paperKey(paper), { paper, rank }));
    return map;
  }, [papers]);
  const targets = scene.points;
  const signature = targets.map((p: any) => `${p.corpusid}:${p.x}:${p.y}`).join("|");
  const shownRef = useRef<Map<string, { x: number; y: number; s: number }>>(new Map());
  const [shown, setShown] = useState<Record<string, { x: number; y: number; s: number }>>({});
  const [settled, setSettled] = useState(false);
  const [groupOpacity, setGroupOpacity] = useState(0);
  const [hover, setHover] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const caption = mapCaption(model);
  const farGroups = farGroupIds(papers, targets);
  const pendingKey = (model.pending_vectors || []).join(",");
  const onLayoutRef = useRef(onLayout);
  onLayoutRef.current = onLayout;

  useEffect(() => {
    if (!query || !pendingKey) return;
    let stop = false;
    let tries = 0;
    let timer = 0;
    const tick = async () => {
      tries += 1;
      try {
        const body = await mapLayout(query);
        if (stop) return;
        if (body?.layout && body.pending === false) {
          onLayoutRef.current?.(body.layout);
          return;
        }
      } catch { /* the first map stays on screen */ }
      if (!stop && tries < 12) timer = window.setTimeout(tick, 700);
    };
    timer = window.setTimeout(tick, 350);
    return () => { stop = true; window.clearTimeout(timer); };
  }, [query, pendingKey]);

  useEffect(() => {
    const reduce = reducedMotion();
    const from = shownRef.current;
    if (reduce || targets.length === 0) {
      const next: Record<string, { x: number; y: number; s: number }> = {};
      targets.forEach((p: any) => { next[String(p.corpusid)] = { x: p.x, y: p.y, s: 1 }; });
      shownRef.current = new Map(Object.entries(next));
      setShown(next);
      setSettled(true);
      setGroupOpacity(1);
      return;
    }
    setSettled(false);
    let raf = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / 720);
      const e = ease(t);
      const next: Record<string, { x: number; y: number; s: number }> = {};
      targets.forEach((p: any) => {
        const id = String(p.corpusid);
        const prev = from.get(id);
        const x0 = prev ? prev.x : p.x;
        const y0 = prev ? prev.y : p.y;
        const s0 = prev ? prev.s : 0;
        next[id] = { x: x0 + (p.x - x0) * e, y: y0 + (p.y - y0) * e, s: s0 + (1 - s0) * Math.min(1, e) };
      });
      shownRef.current = new Map(Object.entries(next));
      setShown(next);
      setGroupOpacity(0.2 + 0.8 * e);
      if (t < 1) raf = requestAnimationFrame(step);
      else setSettled(true);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [signature]);

  const at = (cid: number) => {
    const point = targets.find((p: any) => p.corpusid === cid);
    if (!point) return null;
    return shown[String(cid)] || { x: point.x, y: point.y, s: 1 };
  };
  const regions = scene.groups;
  const years = model.method === "year-citation" ? yearTicks(papers, targets) : [];
  const line = statusLine(papers, states);
  const activeId = selected || hover;
  const activeNum = activeId ? Number(activeId) : null;
  const cardId = selected && byId.has(selected) ? selected : null;
  const cardPaper = cardId ? byId.get(cardId) : null;
  const cardPoint = cardPaper ? targets.find((p: any) => String(p.corpusid) === cardId) : null;
  const cardShown = cardId ? shown[cardId] : null;

  let tipStyle: { left: number; top: number } | null = null;
  if (cardShown && cardPoint && size.w >= 520) {
    const r = (cardPoint.focus ? 11 : 6) + 16;
    let left = sx(cardShown.x) + r;
    let top = sy(cardShown.y) - 28;
    if (left + 300 > size.w) left = Math.max(8, sx(cardShown.x) - 300 - r);
    // RRM-47: the card is up to 280 px tall (CSS); 240 left «Abrir» outside the platina at 1280×800.
    if (top + 288 > size.h) top = Math.max(8, size.h - 288);
    if (top < 8) top = 8;
    tipStyle = { left, top };
  }

  // RRM-49: hover shows the full title. Never with the click card open, never catching the pointer.
  const hoverMeta = hover && !cardId ? byId.get(hover) : null;
  const hoverShown = hoverMeta ? shown[hover!] : null;
  let hoverStyle: { left: number; top: number; transform: string } | null = null;
  if (hoverMeta && hoverShown && hoverShown.s > 0.55) {
    const hx = sx(hoverShown.x);
    const hy = sy(hoverShown.y);
    const left = Math.min(Math.max(8, hx - 130), Math.max(8, size.w - 268));
    hoverStyle = hy > 70 ? { left, top: hy - 12, transform: "translateY(-100%)" } : { left, top: hy + 12, transform: "none" };
  }

  const members = (cluster: number) => targets.filter((point: any) => point.cluster === cluster);
  const taken: { x: number; y: number; w: number; h: number }[] = [];
  const claimLabel = (here: { x: number; y: number }, r: number, text: string, cluster?: number) => {
    const group = regions.find((item: any) => item.id === cluster);
    const place = labelChoices(sx(here.x), sy(here.y), r, text, size.w, size.h).find((opt) => {
      if (taken.some((box) => overlaps(opt.box, box))) return false;
      if (!group) return true;
      const cx = opt.box.x + opt.box.w / 2;
      const cy = opt.box.y + opt.box.h / 2;
      return Math.hypot(cx - sx(group.cx), cy - sy(group.cy)) <= group.r * view.k + 6;
    });
    if (!place) return null;
    taken.push(place.box);
    return place;
  };

  return (
    <div className="platina-wrap" data-live-map data-method={model.method} data-settled={settled ? "1" : "0"} data-count={papers.length} data-pending={pendingKey ? "1" : "0"}>
      <div
        className="platina"
        ref={box}
        tabIndex={0}
        role="application"
        aria-label="Mapa de la ráfaga. Arrastra para mover, rueda para acercar. Un clic abre la tarjeta del paper."
        onKeyDown={onKey}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onClick={(e) => {
          if (drag.current?.moved) return;
          if ((e.target as HTMLElement).closest(".node-dot, .map-tip, button, .minimap, .region")) return;
          setSelected(null);
        }}
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
            <pattern id="live-grid" width="80" height="80" patternUnits="userSpaceOnUse" patternTransform={`translate(${sx(0)} ${sy(0)}) scale(${view.k})`}>
              <path d="M80 0H0V80" fill="none" stroke="#e4ddd0" strokeWidth={1 / view.k} />
            </pattern>
          </defs>
          <rect width={size.w} height={size.h} fill="url(#live-grid)" opacity=".55" />
          {years.some((tick) => tick.label !== "sin año") && (
            <YearAxis years={years} sx={sx} sy={sy} size={size} />
          )}
          {regions.map((group: any) => {
            const ink = clusterHex(group.id);
            const inside = members(group.id);
            const screenR = group.r * view.k;
            const idsIn = inside.map((point: any) => String(point.corpusid));
            const known = idsIn.some((id) => states[id]?.status || states[id]?.stage);
            const have = idsIn.filter((id) => fullText(byId.get(id)?.paper, states[id])).length;
            const far = farGroups.has(String(group.id)) || group.far === true;
            const title = String(group.name || "grupo");
            const tx = sx(group.cx);
            const ty = sy(group.cy);
            const pitch = regions.reduce((best: number, other: any) => {
              if (other.id === group.id) return best;
              const dist = Math.hypot(sx(other.cx) - tx, sy(other.cy) - ty);
              return dist > 8 ? Math.min(best, dist) : best;
            }, 1e9);
            const chord = Math.max(72, (pitch < 1e8 ? pitch : screenR * 2.3) - 12);
            const fitted = fitTitle(title, chord);
            const titleSize = fitted.size;
            const titleText = fitted.text;
            const noun = group.n === 1 ? "paper" : "papers";
            const subFull = known
              ? `${group.n} ${noun} · texto completo de ${have}`
              : `${group.n} ${noun}`;
            const farLine = "menos cercano a tu pregunta";
            const subLine = [11, 10, 9].map((size) => (subFull.length * size * 0.5 <= chord ? { size, text: subFull } : null)).find(Boolean);
            const subText = screenR < 36 ? "" : (subLine?.text || "");
            const subSize = subLine?.size || 11;
            const subGap = titleSize + 3;
            const titleY = ty - screenR - subGap - 4;
            const textW = Math.min(chord, Math.max(titleText.length, subText.length) * titleSize * 0.5);
            if (titleText || subText) taken.push({ x: tx - textW / 2, y: titleY - titleSize, w: textW, h: subGap + (subText ? subSize : 0) + 4 });
            const note = far ? farLine : subText;
            return (
              <g key={`g${group.id}`} className={`region${far ? " is-far" : ""}`} opacity={groupOpacity * (far ? 0.5 : 1)} onClick={() => { if (!drag.current?.moved) animateTo({ k: Math.max(view.k * 1.7, kFit * 2), cx: group.cx, cy: group.cy }); }}>
                <title>{far ? `${subFull}. ${farLine}` : subFull}</title>
                <circle cx={tx} cy={ty} r={screenR} fill={ink} fillOpacity={far ? 0.03 : 0.07} stroke={ink} strokeOpacity={far ? 0.28 : 0.45} strokeWidth={1.5} strokeDasharray="6 6" style={{ pointerEvents: "visibleStroke" }} />
                <g style={{ pointerEvents: "none" }}>
                  {titleText && (
                    <text x={tx} y={titleY} textAnchor="middle" className="region-title" style={{ fontSize: titleSize }}>
                      {titleText}
                    </text>
                  )}
                  {note && (
                    <text x={tx} y={titleY + subGap} textAnchor="middle" className="region-sub" style={{ fontSize: far ? Math.min(subSize, 11) : subSize }}>
                      {note}
                    </text>
                  )}
                </g>
              </g>
            );
          })}
          {(model.links || []).map((edge: any, i: number) => {
            if (activeNum == null || (edge.citing !== activeNum && edge.cited !== activeNum)) return null;
            const a = at(edge.citing);
            const b = at(edge.cited);
            if (!a || !b) return null;
            return <line key={`c${i}`} x1={sx(a.x)} y1={sy(a.y)} x2={sx(b.x)} y2={sy(b.y)} className="edge dash" strokeOpacity={0.45} />;
          })}
          {[...targets].sort((a: any, b: any) => Number(Boolean(b.focus) || b.rank < 10) - Number(Boolean(a.focus) || a.rank < 10)).map((point: any) => {
            const id = String(point.corpusid);
            const meta = byId.get(id);
            if (!meta) return null;
            const here = shown[id] || { x: point.x, y: point.y, s: 0 };
            const focus = Boolean(point.focus) || point.rank < 10;
            const sunk = Boolean(meta.paper.retracted);
            const phase = phaseOf(states[id]?.status);
            const full = fullText(meta.paper, states[id]);
            const ink = sunk ? "#8d2a2a" : clusterHex(point.cluster);
            const r = (focus ? 4.6 : 3) * Math.max(here.s, 0.45);
            const showLabel = here.s > 0.55 && (selected === id || hover === id || focus);
            const label = showLabel ? shortName(meta.paper) : "";
            const namePlace = label ? claimLabel(here, r, label, point.cluster) : null;
            const tag = !namePlace && (selected === id || hover === id) ? (sunk ? "retractado" : meta.paper.survey ? "survey" : "") : "";
            const tagPlace = tag ? claimLabel(here, r, tag, point.cluster) : null;
            return (
              <g
                key={id}
                className={`node-dot${sunk ? " is-sunk" : ""}${focus ? "" : " is-faint"}`}
                opacity={focus ? 1 : 0.55}
                transform={`translate(${sx(here.x)} ${sy(here.y)})`}
                onPointerEnter={() => setHover(id)}
                onPointerLeave={() => setHover((cur) => (cur === id ? null : cur))}
                onClick={(e) => { e.stopPropagation(); if (!drag.current?.moved) setSelected(id); }}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); setSelected(id); } }}
                tabIndex={0}
                role="button"
                aria-label={`${meta.paper.title || id}. ${phase.label}${meta.paper.survey ? ". survey" : ""}${sunk ? ". retractado" : ""}`}
              >
                <circle r={r + (selected === id ? 2.5 : 0)} fill={full ? ink : "#fffdf8"} stroke={ink} strokeWidth={full ? 1 : 1.35} strokeDasharray={full ? undefined : "2 1.5"} />
                {namePlace && <text x={namePlace.x} y={namePlace.y} textAnchor={namePlace.anchor} className="dot-label">{namePlace.text}</text>}
                {tagPlace && <text x={tagPlace.x} y={tagPlace.y} textAnchor={tagPlace.anchor} className="dot-label">{tagPlace.text}</text>}
              </g>
            );
          })}
        </svg>
        <div className="vignette" aria-hidden="true" />
        <p className="map-status" role="status">{papers.length} {papers.length === 1 ? "paper" : "papers"}{pendingKey ? " · afinando grupos" : ""}</p>
        {showLenses && (
          <div className="lenses" role="group" aria-label="Aumento">
            {LENSES.map((l) => <button key={l} type="button" className={lensZ === l ? "on" : ""} onClick={() => animateTo({ k: kFit * l })}>×{l}</button>)}
          </div>
        )}
        {hoverStyle && hoverMeta && (
          <div className="dot-hover" style={hoverStyle} aria-hidden="true">
            <b>{hoverMeta.paper.title || hover}</b>
            {shortName(hoverMeta.paper) && <span>{shortName(hoverMeta.paper)}</span>}
          </div>
        )}
        {cardPaper && (
          <aside className="map-tip" style={tipStyle || undefined} onPointerDown={(e) => e.stopPropagation()}>
            <p className={`phase phase-${phaseOf(states[cardId!]?.status).id}`}>
              {phaseOf(states[cardId!]?.status).label}
              {fullText(cardPaper.paper, states[cardId!]) ? " · texto completo" : " · sin texto completo"}
            </p>
            <h3>{cardPaper.paper.title || cardId}</h3>
            <p className="authors">{authorLine(cardPaper.paper)}</p>
            {cardPaper.paper.survey && <p className="survey-tag">survey</p>}
            {cardPaper.paper.retracted && <p className="retract">retractado</p>}
            {cardPaper.paper.abstract
              ? <p className="tldr">{short(cardPaper.paper.abstract, 220)}</p>
              : cardPaper.paper.tldr
                ? <p className="tldr">{short(cardPaper.paper.tldr, 220)}</p>
                : <p className="small">Sin abstract en el índice.</p>}
            <div className="map-actions">
              <button type="button" className="primary" onClick={() => onOpen(cardId!)}>Abrir</button>
              <button type="button" className="link" onClick={() => onWant(cardId!)}>quiero leer este</button>
            </div>
          </aside>
        )}
      </div>
      <div className="minimap live-minimap" aria-label="Minimapa" onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const box = frame || { minX: 0, minY: 0, maxX: 1600, maxY: 1000 };
        animateTo({ cx: box.minX + ((e.clientX - r.left) / r.width) * (box.maxX - box.minX), cy: box.minY + ((e.clientY - r.top) / r.height) * (box.maxY - box.minY) });
      }}>
        <svg viewBox={frame ? `${frame.minX} ${frame.minY} ${frame.maxX - frame.minX} ${frame.maxY - frame.minY}` : "0 0 1600 1000"}>
          {regions.map((group: any) => <circle key={group.id} cx={group.cx} cy={group.cy} r={group.r} fill={clusterHex(group.id)} fillOpacity={0.08} stroke={clusterHex(group.id)} strokeWidth={6} />)}
          {targets.map((p: any) => {
            const paper = byId.get(String(p.corpusid))?.paper;
            const full = fullText(paper, states[String(p.corpusid)]);
            return <circle key={p.corpusid} cx={p.x} cy={p.y} r={p.focus ? 14 : 7} fill={full ? clusterHex(p.cluster) : "#fffdf8"} stroke={clusterHex(p.cluster)} strokeWidth={4} />;
          })}
          <rect x={view.cx - size.w / view.k / 2} y={view.cy - size.h / view.k / 2} width={size.w / view.k} height={size.h / view.k} className="mm-view" vectorEffect="non-scaling-stroke" />
        </svg>
      </div>
      <p className="map-legend">
        <ProvChip kind={caption.positionKind as any} text={caption.position} title={caption.positionTitle} />
        {" "}Círculo: grupo, por las palabras del título y el abstract. Nombre: uno de los 10 primeros. Punto relleno: texto completo. Anillo punteado: todavía sin ese texto.
        {line ? ` ${line}.` : ""}
        {caption.note ? ` ${caption.note}` : ""}
      </p>
    </div>
  );
}

function authorLine(paper: any) {
  const names = namesOf(paper);
  const who = names.length ? `${names.slice(0, 3).join(", ")}${names.length > 3 ? " et al." : ""}` : "";
  return [who, paper.year, paper.venue, paper.citationcount != null ? `${paper.citationcount} citas` : ""]
    .filter((part) => part != null && part !== "")
    .join(" · ") || "sin año ni citas en el índice";
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
