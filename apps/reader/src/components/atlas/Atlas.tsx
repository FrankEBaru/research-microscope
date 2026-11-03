"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";

function ink(color: string, delay?: string): CSSProperties {
  const style: CSSProperties & Record<string, string> = { ["--c"]: color };
  if (delay) style.animationDelay = delay;
  return style;
}
import { ATLAS_H, ATLAS_W, nearest, related } from "@/lib/atlas.js";
import { nodeLabel } from "@/lib/layout.js";

const FULL_H = ATLAS_H + 40;

function curve(a: { x: number; y: number }, b: { x: number; y: number }) {
  const mx = (a.x + b.x) / 2;
  const my = Math.min(a.y, b.y) - 26 - Math.abs(a.x - b.x) * 0.06;
  return `M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`;
}

function toLocal(svg: SVGSVGElement, clientX: number, clientY: number) {
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const local = pt.matrixTransform(ctm.inverse());
  return { x: local.x, y: local.y };
}

function metaLine(point: any) {
  const tail = [point.venue, point.year].filter(Boolean).join(" ");
  return [point.authorLine, tail].filter(Boolean).join(" · ");
}

export function Legend() {
  return (
    <div className="lg">
      <span className="lg-item"><i className="lg-dot lg-dot--full" aria-hidden="true" />Full text</span>
      <span className="lg-item"><i className="lg-dot lg-dot--abs" aria-hidden="true" />Abstract only</span>
      <span className="lg-item"><i className="lg-t" aria-hidden="true" />Your path</span>
      <span className="lg-item"><i className="lg-c" aria-hidden="true" />Citations</span>
    </div>
  );
}

export default function Atlas({
  model, mode = "full", hereId = "", suggestId = "", selected = "", drawSelection = false, onSelect, onOpen,
}: {
  model: any;
  mode?: "full" | "mini";
  hereId?: string;
  suggestId?: string;
  selected?: string;
  drawSelection?: boolean;
  onSelect?: (id: string) => void;
  onOpen?: (id: string) => void;
}) {
  const mini = mode === "mini";
  const svgRef = useRef<SVGSVGElement | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const pointsRef = useRef<any[]>(model?.points || []);
  const hoverRef = useRef<string | null>(null);
  const selectedRef = useRef(selected || "");
  const hereRef = useRef(hereId);
  const suggestRef = useRef(suggestId);
  const onSelectRef = useRef(onSelect);
  const onOpenRef = useRef(onOpen);
  const [hover, setHover] = useState<string | null>(null);
  const [tip, setTip] = useState<{ id: string; left: number; top: number } | null>(null);
  pointsRef.current = model?.points || [];
  selectedRef.current = selected || "";
  hereRef.current = hereId || "";
  suggestRef.current = suggestId || "";
  onSelectRef.current = onSelect;
  onOpenRef.current = onOpen;

  const show = (id: string | null) => {
    if (hoverRef.current === id) return;
    hoverRef.current = id;
    setHover(id);
  };

  useEffect(() => {
    const svg = svgRef.current;
    const host = hostRef.current;
    if (!svg || !host || mini) return;
    let warm = false;
    let timer = 0;
    let cool = 0;
    let touchArmed: string | null = null;
    const placeTip = (id: string | null) => {
      show(id);
      if (!id) { setTip(null); return; }
      const point = pointsRef.current.find((p) => p.id === id);
      if (!point) { setTip(null); return; }
      const r = svg.getBoundingClientRect();
      const hr = host.getBoundingClientRect();
      const k = r.width / ATLAS_W;
      setTip({ id, left: r.left - hr.left + point.x * k, top: r.top - hr.top + point.y * k });
    };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      const local = toLocal(svg, e.clientX, e.clientY);
      if (!local) return;
      const id = nearest(pointsRef.current, local.x, local.y, 18);
      svg.style.cursor = id ? "pointer" : "default";
      if (id === hoverRef.current) return;
      window.clearTimeout(timer);
      window.clearTimeout(cool);
      if (!id) { placeTip(null); return; }
      if (warm) placeTip(id);
      else timer = window.setTimeout(() => { warm = true; placeTip(id); }, 260);
    };
    const onLeave = () => {
      window.clearTimeout(timer);
      placeTip(null);
      cool = window.setTimeout(() => { warm = false; }, 600);
    };
    const onClick = (e: MouseEvent) => {
      const local = toLocal(svg, e.clientX, e.clientY);
      if (!local) return;
      const id = nearest(pointsRef.current, local.x, local.y, 18);
      const touch = (e as PointerEvent).pointerType === "touch" || window.matchMedia("(hover: none)").matches;
      if (id && touch && touchArmed !== id) {
        touchArmed = id;
        warm = true;
        placeTip(id);
        return;
      }
      touchArmed = null;
      if (id) onSelectRef.current?.(id);
    };
    const onKey = (e: KeyboardEvent) => {
      const points = pointsRef.current;
      const by = new Map(points.map((p) => [p.id, p]));
      const base = selectedRef.current || hereRef.current || suggestRef.current;
      const origin = by.get(base);
      let next: string | null = null;
      if (origin && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        const dir = e.key === "ArrowRight" ? 1 : -1;
        let best = 1e9;
        for (const o of points) {
          const dx = (o.x - origin.x) * dir;
          if (dx > 0) {
            const score = dx + Math.abs(o.y - origin.y) * 2.5;
            if (score < best) { best = score; next = o.id; }
          }
        }
      }
      if (origin && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
        const dir = e.key === "ArrowDown" ? 1 : -1;
        let best = 1e9;
        for (const o of points) {
          const dy = (o.y - origin.y) * dir;
          if (dy > 0) {
            const score = dy + Math.abs(o.x - origin.x) * 2.5;
            if (score < best) { best = score; next = o.id; }
          }
        }
      }
      if (e.key === "ArrowRight" || e.key === "ArrowLeft" || e.key === "ArrowDown" || e.key === "ArrowUp") e.preventDefault();
      if (next) {
        onSelectRef.current?.(next);
        placeTip(next);
      }
      if (e.key === "Enter" && selectedRef.current) {
        e.preventDefault();
        onOpenRef.current?.(selectedRef.current);
      }
      if (e.key === "Escape") placeTip(null);
    };
    svg.addEventListener("pointermove", onMove);
    svg.addEventListener("pointerleave", onLeave);
    svg.addEventListener("click", onClick);
    svg.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(timer);
      window.clearTimeout(cool);
      svg.removeEventListener("pointermove", onMove);
      svg.removeEventListener("pointerleave", onLeave);
      svg.removeEventListener("click", onClick);
      svg.removeEventListener("keydown", onKey);
    };
  }, [mini]);

  const points: any[] = model?.points || [];
  const by = new Map(points.map((p) => [p.id, p]));
  const focus = hover || (drawSelection ? selected : "") || "";
  const fset = (() => {
    if (!focus || !by.has(focus)) return null;
    const set = new Set<string>([focus]);
    for (const id of related(model, focus, 14)) set.add(id);
    return set;
  })();
  const visited = new Set<string>(model?.visited || []);
  const hoverPoint = hover ? by.get(hover) : null;
  const labs = new Set<string>();
  if (!mini) {
    for (const id of visited) if (by.has(id)) labs.add(id);
    if (hereId && by.has(hereId)) labs.add(hereId);
    if (suggestId && by.has(suggestId)) labs.add(suggestId);
    if (selected && by.has(selected)) labs.add(selected);
    if (hover && by.has(hover)) labs.add(hover);
  }
  const here = hereId ? by.get(hereId) : null;
  const sug = suggestId ? by.get(suggestId) : null;
  const sel = selected ? by.get(selected) : null;

  return (
    <div className="atlas" ref={hostRef}>
      <svg
        ref={svgRef}
        className={`atl-svg${mini ? " is-mini" : ""}${fset ? " has-focus" : ""}`}
        viewBox={`0 0 ${ATLAS_W} ${mini ? ATLAS_H : FULL_H}`}
        role={mini ? "img" : "application"}
        aria-label={mini ? "Atlas: papers you explored and where you are" : "Atlas of papers by group and year"}
        tabIndex={mini ? undefined : 0}
      >
        <g className="lanes">
          {(model?.lanes || []).map((lane: any) => (
            <g key={lane.id}>
              <rect className={`lane${lane.far ? " is-far" : ""}`} x={0} y={lane.top} width={ATLAS_W} height={lane.h} rx={mini ? 10 : 6} style={ink(lane.color)} />
              {!mini && lane.name ? <text className="ln-name" x={14} y={lane.top + 22} style={ink(lane.color)}>{lane.name}</text> : null}
              {!mini && lane.name && lane.h >= 52 ? <text className="ln-n" x={14} y={lane.top + 39}>{lane.n} {lane.n === 1 ? "paper" : "papers"}</text> : null}
            </g>
          ))}
        </g>
        {!mini && (model?.years?.ticks?.length || model?.years?.noYearX) ? (
          <g className="grid">
            {(model.years.ticks || []).map((tick: any) => (
              <g key={tick.year}>
                <line x1={tick.x} x2={tick.x} y1={0} y2={ATLAS_H + 8} />
                <text className="yr" x={tick.x} y={ATLAS_H + 30} textAnchor="middle">{tick.year}</text>
              </g>
            ))}
            {model.years.noYearX != null ? <text className="yr" x={model.years.noYearX} y={ATLAS_H + 30} textAnchor="middle">no year</text> : null}
          </g>
        ) : null}
        <g className="cit">
          {!mini && focus && by.has(focus) ? related(model, focus, 14).map((id: string) => {
            const other = by.get(id);
            const from = by.get(focus);
            if (!other || !from) return null;
            return <line key={id} x1={from.x} y1={from.y} x2={other.x} y2={other.y} vectorEffect="non-scaling-stroke" />;
          }) : null}
        </g>
        <g className="trail">
          {(model?.trail || []).map((pair: any) => {
            const a = by.get(pair.from);
            const b = by.get(pair.to);
            if (!a || !b) return null;
            return <path key={`${pair.from}-${pair.to}`} d={curve(a, b)} vectorEffect="non-scaling-stroke" />;
          })}
        </g>
        <g className="halo">
          {here ? <circle className="h-cur" cx={here.x} cy={here.y} r={mini ? 30 : 14} /> : null}
          {sug ? <circle className="h-sug" cx={sug.x} cy={sug.y} r={mini ? 30 : 13} vectorEffect="non-scaling-stroke" /> : null}
          {!mini && sel && sel.id !== hereId ? <circle className="h-sel" cx={sel.x} cy={sel.y} r={11} vectorEffect="non-scaling-stroke" /> : null}
        </g>
        <g className="dots">
          {points.map((point, i) => {
            const vis = visited.has(point.id);
            const cur = point.id === hereId;
            const hot = point.id === focus || point.id === hereId;
            const r = mini ? (vis ? 13 : 8) : (hot ? 6.5 : vis ? 5.6 : 4.6);
            const cls = [
              "p",
              point.full ? "p--f" : "p--h",
              vis ? "is-vis" : "",
              cur ? "is-cur" : "",
              fset && !fset.has(point.id) ? "is-dim" : "",
              fset && fset.has(point.id) && point.id !== focus ? "is-rel" : "",
              point.far ? "is-far" : "",
              point.retracted ? "is-retracted" : "",
            ].filter(Boolean).join(" ");
            return (
              <circle
                key={point.id}
                className={cls}
                data-id={point.id}
                cx={Number(point.x.toFixed(1))}
                cy={Number(point.y.toFixed(1))}
                r={r}
                style={ink(point.color, `${i * 7}ms`)}
              />
            );
          })}
        </g>
        {!mini ? (
          <g className="labs">
            {[...labs].map((id) => {
              const point = by.get(id);
              if (!point) return null;
              const strong = id === hereId || id === selected || id === suggestId;
              const dim = Boolean(fset && !fset.has(id) && id !== hereId);
              const label = nodeLabel({ authors: point.authors, year: point.year, title: point.title });
              return (
                <text
                  key={id}
                  className={`p-lab${strong ? " p-lab--sel" : ""}${dim ? " is-dim" : ""}`}
                  x={point.x + (strong ? 17 : 10)}
                  y={point.y + (strong ? 5 : -8)}
                >{label}</text>
              );
            })}
          </g>
        ) : null}
      </svg>
      {!mini && tip && hoverPoint ? (
        <div className={`peek${hoverPoint.x > ATLAS_W * 0.62 ? " is-flip" : ""}`} role="tooltip" style={{ left: tip.left, top: tip.top }}>
          <b>{hoverPoint.title || "Paper"}</b>
          {metaLine(hoverPoint) ? <span>{metaLine(hoverPoint)}</span> : null}
          <span className="tip-n">Cites {hoverPoint.cites.length} · cited by {hoverPoint.citedBy.length} in this map</span>
        </div>
      ) : null}
    </div>
  );
}
