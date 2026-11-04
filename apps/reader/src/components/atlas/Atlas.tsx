"use client";
import { memo, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ATLAS_H, ATLAS_W, nearest, readingOrder, related } from "@/lib/atlas.js";
import { nodeLabel } from "@/lib/layout.js";
import { Rich } from "@/lib/math";

// RRM-95. Hover never re-renders the dots: the dot layer is memoized and the
// focus set is applied as classes straight on the SVG nodes. Only the small
// hover layer (citation lines, ring, tooltip) re-renders on pointer move.

const FULL_H = ATLAS_H + 40;

function ink(color: string, extra?: Record<string, string>): CSSProperties {
  return { ["--c" as string]: color, ...(extra || {}) } as CSSProperties;
}

function curve(a: { x: number; y: number }, b: { x: number; y: number }) {
  const mx = (a.x + b.x) / 2;
  const my = Math.min(a.y, b.y) - 26 - Math.abs(a.x - b.x) * 0.06;
  return `M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`;
}

function toLocal(svg: SVGSVGElement, clientX: number, clientY: number) {
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const pt = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
  return { x: pt.x, y: pt.y };
}

function metaLine(point: any) {
  const tail = [point.venue, point.year].filter(Boolean).join(" ");
  const names: string[] = point.authors || [];
  const who = names.length > 3 ? `${names.slice(0, 2).join(", ")} et al.` : names.join(", ");
  return [who, tail].filter(Boolean).join(" · ");
}

/** Short on-map name: "Vaswani 2017" when authors are known, else a clipped title. */
function shortLabel(point: any) {
  const label = nodeLabel({ authors: point.authors, year: point.year, title: point.title });
  if (label.length <= 30) return label;
  return label.slice(0, 28).replace(/\s+\S*$/, "") + "…";
}

export function Legend() {
  return (
    <div className="lg" aria-hidden="true">
      <span className="lg-item"><i className="lg-n">1</i>Read first</span>
      <span className="lg-item"><i className="lg-dot lg-dot--full" />Full text</span>
      <span className="lg-item"><i className="lg-dot lg-dot--abs" />Abstract only</span>
      <span className="lg-item"><i className="lg-size" />More cited</span>
      <span className="lg-item"><i className="lg-t" />Your path</span>
      <span className="lg-item"><i className="lg-c" />Citations</span>
    </div>
  );
}

type Pt = any;

const Lanes = memo(function Lanes({ lanes, mini, laneId, years }: { lanes: any[]; mini: boolean; laneId: string; years: any }) {
  return (
    <>
      <g className="lanes">
        {lanes.map((lane, i) => (
          <g key={lane.id} className="ln" style={{ ["--i" as string]: String(i) } as CSSProperties}>
            <rect className={`lane${lane.far ? " is-far" : ""}${laneId && !mini && lane.id !== laneId ? " is-quiet" : ""}${laneId && !mini && lane.id === laneId ? " is-pick" : ""}`} x={0} y={lane.top} width={ATLAS_W} height={lane.h} rx={mini ? 10 : 6} style={ink(lane.color)} />
            {!mini && lane.name ? <text key={lane.name} className="ln-name" x={14} y={lane.top + 23} style={ink(lane.color)}>{lane.name}</text> : null}
            {!mini && lane.name && lane.h >= 52 ? <text className="ln-n" x={14} y={lane.top + 41}>{lane.n} {lane.n === 1 ? "paper" : "papers"}</text> : null}
          </g>
        ))}
      </g>
      {!mini && (years?.ticks?.length || years?.noYearX != null) ? (
        <g className="grid">
          {(years.ticks || []).map((tick: any) => (
            <g key={tick.year}>
              <line x1={tick.x} x2={tick.x} y1={0} y2={ATLAS_H + 8} />
              <text className="yr" x={tick.x} y={ATLAS_H + 30} textAnchor="middle">{tick.year}</text>
            </g>
          ))}
          {years.earlierX != null ? <text className="yr yr--soft" x={years.earlierX} y={ATLAS_H + 30} textAnchor="middle">{`< ${years.cut}`}</text> : null}
          {years.noYearX != null ? <text className="yr yr--soft" x={years.noYearX} y={ATLAS_H + 30} textAnchor="middle">no year</text> : null}
        </g>
      ) : null}
    </>
  );
});

const Dots = memo(function Dots({ points, visited, hereId, mini, laneId }: { points: Pt[]; visited: string[]; hereId: string; mini: boolean; laneId: string }) {
  const seen = new Set(visited);
  // Arrival sweeps left to right in time, like the field being written.
  return (
    <g className="dots">
      {points.map((point) => {
        const vis = seen.has(point.id);
        const cur = point.id === hereId;
        const r = mini ? (vis ? 13 : 8) : point.r || 4.6;
        const cls = [
          "p",
          point.full ? "p--f" : "p--h",
          vis ? "is-vis" : "",
          cur ? "is-cur" : "",
          !mini && point.order && point.order <= 5 ? "is-top" : "",
          laneId && !mini && point.lane && point.lane !== laneId ? "is-out" : "",
          point.far ? "is-far" : "",
          point.retracted ? "is-retracted" : "",
        ].filter(Boolean).join(" ");
        const delay = Math.round((point.x / ATLAS_W) * 620 + (point.y % 37) * 2);
        return (
          <circle
            key={point.id}
            className={cls}
            data-id={point.id}
            data-read={!mini && point.order && point.order <= 5 ? point.order : undefined}
            cx={Number(point.x.toFixed(1))}
            cy={Number(point.y.toFixed(1))}
            r={r}
            style={ink(point.color, { animationDelay: `${delay}ms` })}
          />
        );
      })}
    </g>
  );
});

const Badges = memo(function Badges({ points }: { points: Pt[] }) {
  return (
    <g className="ords">
      {points.filter((p) => p.order && p.order <= 5).map((point) => (
        <text key={point.id} className="p-ord" x={point.x} y={point.y + 3.6} textAnchor="middle" style={{ animationDelay: `${Math.round((point.x / ATLAS_W) * 620) + 260}ms` }}>{point.order}</text>
      ))}
    </g>
  );
});

/** Persistent labels: the first three of the reading order and the papers you touched. Skips any that would collide. */
const Labels = memo(function Labels({ points, ids, strongIds }: { points: Pt[]; ids: string[]; strongIds: string[] }) {
  const by = new Map(points.map((p) => [p.id, p]));
  const strong = new Set(strongIds);
  const boxes: { x0: number; x1: number; y0: number; y1: number }[] = [];
  // Badges and labeled dots are obstacles too.
  for (const p of points) {
    if ((p.order && p.order <= 5) || ids.includes(p.id)) {
      const r = (p.r || 5) + 1;
      boxes.push({ x0: p.x - r, x1: p.x + r, y0: p.y - r, y1: p.y + r });
    }
  }
  const out: any[] = [];
  for (const id of ids) {
    const p = by.get(id);
    if (!p) continue;
    const text = shortLabel(p);
    const w = text.length * 6.6 + 6;
    const hits = (bx: { x0: number; x1: number; y0: number; y1: number }) => boxes.some((b) => b.x0 < bx.x1 && bx.x0 < b.x1 && b.y0 < bx.y1 && bx.y0 < b.y1);
    const place = (right: boolean) => {
      const x = right ? p.x + (p.r || 5) + 5 : p.x - (p.r || 5) - 5;
      return { right, x, box: { x0: right ? x : x - w, x1: right ? x + w : x, y0: p.y - 8, y1: p.y + 8 } };
    };
    const first = place(p.x + w + 16 < ATLAS_W);
    const pick = !hits(first.box) ? first : !hits(place(!first.right).box) && (first.right ? p.x - w > 0 : true) ? place(!first.right) : null;
    if (!pick) continue;
    const { right, x, box } = pick;
    boxes.push(box);
    out.push(
      <text key={id} data-for={id} className={`p-lab${strong.has(id) ? " p-lab--sel" : ""}`} x={x} y={p.y + 4} textAnchor={right ? "start" : "end"}>{text}</text>,
    );
  }
  return <g className="labs">{out}</g>;
});

export default function Atlas({
  model, mode = "full", hereId = "", suggestId = "", selected = "", drawSelection = false, laneId = "", onSelect, onOpen,
}: {
  model: any;
  mode?: "full" | "mini";
  hereId?: string;
  suggestId?: string;
  selected?: string;
  drawSelection?: boolean;
  laneId?: string;
  onSelect?: (id: string) => void;
  onOpen?: (id: string) => void;
}) {
  const mini = mode === "mini";
  const svgRef = useRef<SVGSVGElement | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const points: Pt[] = model?.points || [];
  const pointsRef = useRef<Pt[]>(points);
  const hoverRef = useRef<string | null>(null);
  const selectedRef = useRef(selected || "");
  const hereRef = useRef(hereId);
  const suggestRef = useRef(suggestId);
  const onSelectRef = useRef(onSelect);
  const onOpenRef = useRef(onOpen);
  const [hover, setHover] = useState<string | null>(null);
  pointsRef.current = points;
  selectedRef.current = selected || "";
  hereRef.current = hereId || "";
  suggestRef.current = suggestId || "";
  onSelectRef.current = onSelect;
  onOpenRef.current = onOpen;

  const by = useMemo(() => new Map(points.map((p) => [p.id, p])), [points]);
  const focus = hover || (drawSelection ? selected : "") || "";
  const rel = useMemo(() => (focus && by.has(focus) ? related(model, focus, 14) : []), [model, by, focus]);

  // Focus classes go straight onto the DOM: no re-render of ~100 circles per move.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || mini) return;
    svg.querySelectorAll(".p.is-on, .p.is-focus, .p-lab.is-on").forEach((el) => el.classList.remove("is-on", "is-focus"));
    if (!focus) { svg.classList.remove("has-focus"); return; }
    svg.classList.add("has-focus");
    const mark = (id: string, cls: string) => {
      svg.querySelector(`.p[data-id="${CSS.escape(id)}"]`)?.classList.add(cls);
      svg.querySelector(`.p-lab[data-for="${CSS.escape(id)}"]`)?.classList.add("is-on");
    };
    mark(focus, "is-focus");
    for (const id of rel) mark(id, "is-on");
    for (const id of [hereId, suggestId]) if (id) svg.querySelector(`.p-lab[data-for="${CSS.escape(id)}"]`)?.classList.add("is-on");
  }, [focus, rel, mini, hereId, suggestId, points]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || mini) return;
    let touchArmed: string | null = null;
    const show = (id: string | null) => {
      if (hoverRef.current === id) return;
      hoverRef.current = id;
      setHover(id);
    };
    let raf = 0;
    let last: PointerEvent | null = null;
    const step = () => {
      raf = 0;
      if (!last) return;
      const local = toLocal(svg, last.clientX, last.clientY);
      if (!local) return;
      const id = nearest(pointsRef.current, local.x, local.y, 18);
      svg.style.cursor = id ? "pointer" : "default";
      show(id);
    };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      last = e;
      if (!raf) raf = requestAnimationFrame(step);
    };
    const onLeave = () => { last = null; show(null); };
    const onClick = (e: MouseEvent) => {
      const hit = (e.target as Element | null)?.closest?.(".trail-hit");
      if (hit) {
        const id = hit.getAttribute("data-to") || "";
        if (id) onOpenRef.current?.(id);
        return;
      }
      const local = toLocal(svg, e.clientX, e.clientY);
      if (!local) return;
      const id = nearest(pointsRef.current, local.x, local.y, 18);
      const touch = (e as PointerEvent).pointerType === "touch" || window.matchMedia("(hover: none)").matches;
      if (id && touch && touchArmed !== id) {
        touchArmed = id;
        show(id);
        return;
      }
      touchArmed = null;
      if (id) onSelectRef.current?.(id);
    };
    const onDbl = (e: MouseEvent) => {
      const local = toLocal(svg, e.clientX, e.clientY);
      const id = local ? nearest(pointsRef.current, local.x, local.y, 18) : null;
      if (id) onOpenRef.current?.(id);
    };
    const onKey = (e: KeyboardEvent) => {
      const list = pointsRef.current;
      const map = new Map(list.map((p) => [p.id, p]));
      const base = selectedRef.current || hereRef.current || suggestRef.current;
      const origin = map.get(base);
      let next: string | null = null;
      const arrows: Record<string, [number, number]> = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] };
      const dir = arrows[e.key];
      if (dir) {
        e.preventDefault();
        if (origin) {
          let best = 1e9;
          for (const o of list) {
            const along = dir[0] ? (o.x - origin.x) * dir[0] : (o.y - origin.y) * dir[1];
            const across = dir[0] ? Math.abs(o.y - origin.y) : Math.abs(o.x - origin.x);
            if (along > 0) {
              const score = along + across * 2.5;
              if (score < best) { best = score; next = o.id; }
            }
          }
        }
      }
      if (next) { onSelectRef.current?.(next); show(next); }
      if (e.key === "Enter" && selectedRef.current) { e.preventDefault(); onOpenRef.current?.(selectedRef.current); }
      if (e.key === "Escape") show(null);
    };
    svg.addEventListener("pointermove", onMove);
    svg.addEventListener("pointerleave", onLeave);
    svg.addEventListener("click", onClick);
    svg.addEventListener("dblclick", onDbl);
    svg.addEventListener("keydown", onKey);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      svg.removeEventListener("pointermove", onMove);
      svg.removeEventListener("pointerleave", onLeave);
      svg.removeEventListener("click", onClick);
      svg.removeEventListener("dblclick", onDbl);
      svg.removeEventListener("keydown", onKey);
    };
  }, [mini]);

  const visited: string[] = model?.visited || [];
  const labelIds = useMemo(() => {
    if (mini) return [];
    const ids: string[] = [];
    const add = (id: string) => { if (id && by.has(id) && !ids.includes(id)) ids.push(id); };
    add(hereId); add(selected); add(suggestId);
    for (const id of visited) add(id);
    for (const row of readingOrder(points).slice(0, 3)) add(row.id);
    return ids;
  }, [mini, by, hereId, selected, suggestId, visited, points]);
  const strongIds = useMemo(() => [hereId, selected, suggestId].filter(Boolean), [hereId, selected, suggestId]);

  const here = hereId ? by.get(hereId) : null;
  const sug = suggestId ? by.get(suggestId) : null;
  const sel = selected ? by.get(selected) : null;
  const fp = focus ? by.get(focus) : null;
  const hoverPoint = hover ? by.get(hover) : null;
  const scale = (() => {
    const svg = svgRef.current;
    if (!svg) return 1;
    const w = svg.getBoundingClientRect().width;
    return w ? w / ATLAS_W : 1;
  })();

  return (
    <div className={`atlas${mini ? "" : " is-live"}`} ref={hostRef}>
      <svg
        ref={svgRef}
        className={`atl-svg${mini ? " is-mini" : ""}`}
        viewBox={`0 0 ${ATLAS_W} ${mini ? ATLAS_H : FULL_H}`}
        role={mini ? "img" : "application"}
        aria-label={mini ? "Atlas: papers you explored and where you are" : "Atlas of papers by group and year"}
        tabIndex={mini ? undefined : 0}
      >
        <Lanes lanes={model?.lanes || []} mini={mini} laneId={laneId} years={model?.years} />
        <g className="cit">
          {!mini && fp ? rel.map((id: string) => {
            const other = by.get(id);
            if (!other) return null;
            const out = fp.cites.includes(id);
            return <line key={id} className={out ? "is-out" : "is-in"} x1={fp.x} y1={fp.y} x2={other.x} y2={other.y} vectorEffect="non-scaling-stroke" />;
          }) : null}
        </g>
        <g className="trail">
          {(model?.trail || []).map((pair: any, i: number) => {
            const a = by.get(pair.from);
            const b = by.get(pair.to);
            if (!a || !b) return null;
            const d = curve(a, b);
            return (
              <g key={`${pair.from}-${pair.to}`}>
                <path className="trail-draw" d={d} pathLength={1} vectorEffect="non-scaling-stroke" style={{ animationDelay: `${700 + i * 120}ms` }} />
                {!mini ? <path className="trail-hit" data-to={pair.to} d={d} vectorEffect="non-scaling-stroke"><title>{`Open ${b.title || "paper"}`}</title></path> : null}
              </g>
            );
          })}
        </g>
        <g className="halo">
          {here ? <circle className="h-cur" cx={here.x} cy={here.y} r={mini ? 30 : (here.r || 5) + 8} /> : null}
          {sug ? <circle className="h-sug" cx={sug.x} cy={sug.y} r={mini ? 30 : (sug.r || 5) + 6} vectorEffect="non-scaling-stroke" /> : null}
          {!mini && sel && sel.id !== hereId ? <circle className="h-sel" cx={sel.x} cy={sel.y} r={(sel.r || 5) + 4} vectorEffect="non-scaling-stroke" /> : null}
        </g>
        <Dots points={points} visited={visited} hereId={hereId} mini={mini} laneId={laneId} />
        {!mini ? <Badges points={points} /> : null}
        {!mini ? <Labels points={points} ids={labelIds} strongIds={strongIds} /> : null}
        {!mini && fp ? <circle className="h-hov" cx={fp.x} cy={fp.y} r={(fp.r || 5) + 3.5} vectorEffect="non-scaling-stroke" /> : null}
      </svg>
      {!mini && hoverPoint ? (
        <div
          className={`peek${hoverPoint.x > ATLAS_W * 0.62 ? " is-flip" : ""}${hoverPoint.y < 90 ? " is-below" : ""}`}
          role="tooltip"
          style={{ left: hoverPoint.x * scale, top: hoverPoint.y * scale, ["--c" as string]: hoverPoint.color } as CSSProperties}
        >
          <b><Rich text={hoverPoint.title || "Paper"} /></b>
          {metaLine(hoverPoint) ? <span>{metaLine(hoverPoint)}</span> : null}
          <span className="tip-row tnum">
            {hoverPoint.order && hoverPoint.order <= 5 ? <em>Read {hoverPoint.order === 1 ? "first" : `#${hoverPoint.order}`}</em> : null}
            {hoverPoint.citations ? <span>{hoverPoint.citations.toLocaleString("en-US")} citations</span> : null}
            <span>{hoverPoint.cites.length} out · {hoverPoint.citedBy.length} in, here</span>
          </span>
        </div>
      ) : null}
    </div>
  );
}

/** The first papers in the search rank, numbered the same way as the dots. */
export function ReadFirst({ points, onPick, selected = "" }: { points: any[]; onPick?: (id: string) => void; selected?: string }) {
  const rows = readingOrder(points).slice(0, 5);
  if (!rows.length) return null;
  const by = new Map((points || []).map((point) => [point.id, point]));
  return (
    <ol className="read-first" aria-label="Reading order">
      {rows.map((row) => {
        const point = by.get(row.id);
        return (
          <li key={row.id}>
            <button type="button" className={row.id === selected ? "is-sel" : undefined} onClick={() => onPick?.(row.id)}>
              <span className="rf-n">{row.n}</span>
              <span className="rf-t"><Rich text={point?.title || row.id} /></span>
              {point?.year ? <span className="rf-y tnum">{point.year}</span> : null}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
