"use client";
import { useEffect, useRef, useState } from "react";
import "@/styles/inicio.css";
import { Icon } from "../ui";

const ROWS = [
  { id: "wake", label: "Waking the search engine" },
  { id: "search", label: "Finding papers" },
  { id: "layout", label: "Arranging the atlas" },
] as const;

type PhaseId = (typeof ROWS)[number]["id"];

function activePhase(engine: string, phase: string, pending: boolean): PhaseId | "" {
  if (phase === "layout" || phase === "search" || phase === "wake") return phase;
  if (engine === "preparando") return "wake";
  if (pending) return "search";
  return "";
}

function clock(sec: number) {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const LANES = [
  { y: 0, h: 56, c: "var(--grp-2)" },
  { y: 60, h: 40, c: "var(--grp-3)" },
  { y: 104, h: 28, c: "var(--grp-1)" },
  { y: 136, h: 14, c: "var(--grp-4)" },
];

function formingDots() {
  let seed = 5;
  const rnd = () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };
  const counts = [17, 11, 7];
  const dots: { cx: string; cy: string; r: number; kind: string; c: string; delay: number }[] = [];
  let n = 0;
  LANES.slice(0, 3).forEach((lane, index) => {
    for (let i = 0; i < counts[index]; i++) {
      dots.push({
        cx: (40 + rnd() * 460).toFixed(1),
        cy: (lane.y + 7 + rnd() * (lane.h - 14)).toFixed(1),
        r: rnd() < 0.3 ? 4 : 3,
        kind: rnd() < 0.35 ? "f" : "h",
        c: lane.c,
        delay: n++ * 80,
      });
    }
  });
  return dots;
}

const DOTS = formingDots();

export function Forming({ still }: { still?: boolean }) {
  return (
    <figure className={still ? "forming forming--quiet" : "forming"} aria-hidden="true">
      <svg viewBox="0 0 520 150" width="100%" height="150">
        <g className="lanes">
          {LANES.map((lane) => (
            <rect key={lane.c} y={lane.y} width="520" height={lane.h} fill={lane.c} />
          ))}
        </g>
        <g className={still ? "ar is-still" : "ar"}>
          {DOTS.map((dot, i) => (
            <circle
              key={i}
              cx={dot.cx}
              cy={dot.cy}
              r={dot.r}
              className={dot.kind}
              style={{ ["--c" as string]: dot.c, animationDelay: `${dot.delay}ms` }}
            />
          ))}
        </g>
      </svg>
    </figure>
  );
}

/** RRM-95: the map frame while the search runs — lanes and dots forming where the atlas will land. */
const ATLAS_DOTS = (() => {
  let seed = 11;
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  const lanes = [{ y: 0, h: 150 }, { y: 156, h: 190 }, { y: 352, h: 148 }];
  const out: { cx: number; cy: number; r: number; f: boolean; lane: number; d: number }[] = [];
  lanes.forEach((lane, li) => {
    for (let i = 0; i < 26; i++) {
      const x = 180 + Math.pow(rnd(), 0.6) * 690;
      out.push({ cx: x, cy: lane.y + 14 + rnd() * (lane.h - 28), r: 3.5 + rnd() * 3, f: rnd() < 0.3, lane: li, d: Math.round((x / 900) * 1100 + rnd() * 500) });
    }
  });
  return { lanes, dots: out };
})();

export function FormingAtlas() {
  const C = ["var(--grp-1)", "var(--grp-2)", "var(--grp-3)"];
  return (
    <figure className="forming-atlas" aria-hidden="true">
      <svg viewBox="0 0 900 540" width="100%">
        {ATLAS_DOTS.lanes.map((lane, i) => <rect key={i} className="fa-lane" x={0} y={lane.y} width={900} height={lane.h} rx={6} style={{ ["--c" as string]: C[i], animationDelay: `${i * 90}ms` } as React.CSSProperties} />)}
        {ATLAS_DOTS.lanes.map((lane, i) => <rect key={`t${i}`} className="fa-label" x={14} y={lane.y + 14} width={110 + i * 22} height={9} rx={4.5} />)}
        <g className="ar is-still">
          {ATLAS_DOTS.dots.map((d, i) => <circle key={i} cx={d.cx} cy={d.cy} r={d.r} className={d.f ? "f" : "h"} style={{ ["--c" as string]: C[d.lane], animationDelay: `${d.d}ms` } as React.CSSProperties} />)}
        </g>
        {[0, 1, 2, 3, 4, 5, 6].map((i) => <rect key={`y${i}`} className="fa-label" x={230 + i * 105} y={518} width={30} height={8} rx={4} />)}
      </svg>
    </figure>
  );
}

export default function BootPanel({ engine, phase, pending, compact }: {
  engine: string;
  phase: string;
  pending: boolean;
  compact?: boolean;
}) {
  const active = activePhase(engine, phase, pending);
  const started = useRef(Date.now());
  const entered = useRef(Date.now());
  const prev = useRef<PhaseId | "">("");
  const [spent, setSpent] = useState<Partial<Record<PhaseId, number>>>({});
  const [seenLayout, setSeenLayout] = useState(phase === "layout");
  const [now, setNow] = useState(0);
  const [clockOn, setClockOn] = useState(false);

  useEffect(() => {
    if (phase === "layout") setSeenLayout(true);
  }, [phase]);

  useEffect(() => {
    const nowMs = Date.now();
    if (prev.current && prev.current !== active) {
      const sec = (nowMs - entered.current) / 1000;
      const doneId = prev.current;
      setSpent((cur) => ({ ...cur, [doneId]: sec }));
      entered.current = nowMs;
    } else if (!prev.current) {
      entered.current = nowMs;
    }
    prev.current = active;
  }, [active]);

  useEffect(() => {
    setClockOn(true);
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 200);
    return () => window.clearInterval(id);
  }, [active]);

  if (!active && compact) return null;
  if (!active) return <Forming still />;

  const order: PhaseId[] = ["wake", "search", "layout"];
  const at = order.indexOf(active as PhaseId);
  const rows = ROWS.filter((row) => row.id !== "layout" || seenLayout || active === "layout");

  return (
    <section className={compact ? "boot boot--compact" : "boot"} aria-live="polite" aria-label="Starting up">
      <header className="boot-h">
        <h2>Starting up</h2>
        <p className="b1-clock tnum">{clock(clockOn && now ? (now - started.current) / 1000 : 0)}</p>
      </header>
      <ol className="b1-steps">
        {rows.map((row) => {
          const index = order.indexOf(row.id);
          const state = index < at ? "done" : index === at ? "run" : "wait";
          const sec = state === "run" ? (clockOn && now ? (now - entered.current) / 1000 : 0) : spent[row.id] ?? 0;
          return (
            <li key={row.id} className={state === "done" ? "is-done" : state === "run" ? "is-run" : undefined}>
              <span className="st-i" aria-hidden="true">{state === "done" && <Icon name="check" size={13} />}</span>
              <span className="st-t">{row.label}</span>
              <span className="st-v tnum">{state === "wait" ? "—" : clock(sec)}</span>
              <span className="st-bar" />
            </li>
          );
        })}
      </ol>
      {!compact && <Forming />}
    </section>
  );
}
