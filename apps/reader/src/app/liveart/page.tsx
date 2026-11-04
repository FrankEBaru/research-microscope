"use client";

import { useEffect, useRef, useState } from "react";
import { fallbackText } from "@/lib/liveart/fallback.js";
import { mountSandbox } from "@/lib/liveart/mount.js";
import { GOLD } from "@/lib/liveart/gold.js";
import { ROUND } from "@/lib/liveart/round.js";
import { SHOWCASE } from "@/lib/liveart/showcase.js";
import { VERSION, VERSION_04, liveOn, v04On } from "@/lib/liveart/spec.js";
import { V04 } from "@/lib/liveart/v04.js";
import { Tex } from "@/lib/math";
import "@/styles/liveart.css";

type Knob = {
  id: string;
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  kind?: string;
  options?: string[];
  prompt?: string;
  answer?: number;
};

type Noted = { equation?: string; anchor?: string; cite?: string };

// rrm-widget/0.4 (RRM-90): host blocks painted around the canvas. Only with RRM_LIVEART_V04 on.
type Read = { id: string; label: string; digits?: number; unit?: string; format?: string; color?: string; show?: boolean };
type Anchor04 = { latex?: string; quote?: string; arxiv?: string; section?: string; eq?: string };
type Wide = {
  version?: string;
  hook?: string;
  readouts?: Read[];
  legend?: { color: string; text: string }[];
  takeaway?: string | Record<string, string>;
  anchor?: string | Anchor04;
  equation?: string;
  cite?: string;
};
type Frame = { readouts: Record<string, number>; say: string | null; cmarks: { control: string; label?: string; value: number }[] } | null;

const V04_ON = v04On();

function fmtRead(r: Read | undefined, v: number) {
  if (r && r.format === "pct") return (v * 100).toFixed(r.digits ?? 0) + "%";
  return v.toFixed(r && r.digits != null ? r.digits : 2) + (r && r.unit ? r.unit : "");
}

function takeawayText(w: Wide, frame: Frame, vals: Record<string, number>) {
  if (!frame || !w.takeaway) return "";
  const tpl = typeof w.takeaway === "string" ? w.takeaway : (frame.say && w.takeaway[frame.say]) || "";
  return tpl.replace(/\{(\w+)\}/g, (_, k: string) => {
    const r = (w.readouts || []).find((q) => q.id === k);
    if (r && k in frame.readouts) return fmtRead(r, frame.readouts[k]);
    return k in vals ? String(vals[k]) : "";
  });
}

function noted(w: Wide): Noted {
  if (w.anchor && typeof w.anchor === "object") {
    const a = w.anchor;
    return { equation: a.latex, anchor: a.quote, cite: [a.arxiv ? "arXiv " + a.arxiv : "", a.section || "", a.eq || ""].filter(Boolean).join(" · ") };
  }
  return { equation: w.equation, anchor: typeof w.anchor === "string" ? w.anchor : undefined, cite: w.cite };
}

// RRM-90: the quality round (#59/#64) plus #57's figures and contract examples.
const CATALOG = [
  ...(V04_ON ? V04 : []),
  ...ROUND,
  ...SHOWCASE.map((item) => ({ ...item, source: "figure" })),
  ...GOLD.map((widget) => ({ widget, claim: "", source: "contract" })),
];

function kicker(source: string) {
  if (source === "round") return "Quality round";
  if (source === "v04") return "Live figure " + VERSION_04;
  if (source === "figure") return "Figure";
  if (source === "contract") return "Contract example";
  return "Current figure";
}

function decimals(step: number) {
  const text = String(step);
  const dot = text.indexOf(".");
  return dot < 0 ? 0 : text.length - dot - 1;
}

function kindOf(control: Knob) {
  return control.kind || "slider";
}

function Control({ control, value, set }: { control: Knob; value: number; set: (value: number) => void }) {
  const kind = kindOf(control);
  const pad = useRef<HTMLDivElement | null>(null);
  if (kind === "slider") {
    return (
      <label>
        <span>{control.label}</span>
        <strong>{value.toFixed(decimals(control.step))}</strong>
        <input
          type="range"
          min={control.min}
          max={control.max}
          step={control.step}
          value={value}
          aria-label={control.label}
          onChange={(event) => set(Number(event.target.value))}
        />
      </label>
    );
  }
  if (kind === "toggle" || kind === "play") {
    const on = value >= 0.5;
    return (
      <div className="liveart-choice" data-kind={kind}>
        <button type="button" aria-pressed={on} aria-label={control.label} onClick={() => set(on ? 0 : 1)}>
          {control.label}: {on ? "on" : "off"}
        </button>
        <input className="liveart-fallback-range" type="range" min={0} max={1} step={1} value={on ? 1 : 0} aria-label={`${control.label} slider`} onChange={(event) => set(Number(event.target.value))} />
      </div>
    );
  }
  if (kind === "select" || kind === "pick") {
    const options = control.options || [];
    return (
      <div className="liveart-choice" data-kind={kind}>
        <span>{control.label}</span>
        {kind === "select" ? (
          <select aria-label={control.label} value={value} onChange={(event) => set(Number(event.target.value))}>
            {options.map((option, index) => <option key={option} value={control.min + index * control.step}>{option}</option>)}
          </select>
        ) : (
          <div className="liveart-picks" role="group" aria-label={control.label}>
            {Array.from({ length: Math.round((control.max - control.min) / control.step) + 1 }, (_, index) => {
              const next = control.min + index * control.step;
              return <button key={next} type="button" aria-pressed={value === next} onClick={() => set(next)}>{options[index] || String(next)}</button>;
            })}
          </div>
        )}
        <input className="liveart-fallback-range" type="range" min={control.min} max={control.max} step={control.step} value={value} aria-label={`${control.label} slider`} onChange={(event) => set(Number(event.target.value))} />
      </div>
    );
  }
  if (kind === "button") {
    return (
      <div className="liveart-choice" data-kind="button">
        <button type="button" aria-label={control.label} onClick={() => set(value + control.step > control.max ? control.min : value + control.step)}>
          {control.label} · {value.toFixed(0)}
        </button>
        <input className="liveart-fallback-range" type="range" min={control.min} max={control.max} step={control.step} value={value} aria-label={`${control.label} slider`} onChange={(event) => set(Number(event.target.value))} />
      </div>
    );
  }
  if (kind === "predict") {
    const options = control.options || [];
    return (
      <div className="liveart-choice" data-kind="predict">
        <span>{control.prompt || control.label}</span>
        <div className="liveart-picks" role="group" aria-label={control.label}>
          {options.map((option, index) => {
            const next = index + 1;
            return <button key={option} type="button" aria-pressed={value === next} onClick={() => set(next)}>{option}</button>;
          })}
        </div>
        <input className="liveart-fallback-range" type="range" min={control.min} max={control.max} step={control.step} value={value} aria-label={`${control.label} slider`} onChange={(event) => set(Number(event.target.value))} />
      </div>
    );
  }
  return (
    <div className="liveart-choice" data-kind="drag">
      <span>{control.label}</span>
      <strong>{value.toFixed(decimals(control.step))}</strong>
      <div
        className="liveart-pad"
        ref={pad}
        tabIndex={0}
        role="slider"
        aria-label={control.label}
        aria-valuemin={control.min}
        aria-valuemax={control.max}
        aria-valuenow={value}
        onPointerDown={(event) => {
          const rect = pad.current?.getBoundingClientRect();
          if (!rect) return;
          const span = event.currentTarget.dataset.axis === "y" ? event.clientY - rect.top : event.clientX - rect.left;
          const size = event.currentTarget.dataset.axis === "y" ? rect.height : rect.width;
          const unit = Math.min(1, Math.max(0, span / size));
          set(control.min + unit * (control.max - control.min));
        }}
        onKeyDown={(event) => {
          const delta = event.key === "ArrowRight" || event.key === "ArrowUp" ? control.step : event.key === "ArrowLeft" || event.key === "ArrowDown" ? -control.step : 0;
          if (!delta) return;
          event.preventDefault();
          set(Math.min(control.max, Math.max(control.min, value + delta)));
        }}
      />
      <input className="liveart-fallback-range" type="range" min={control.min} max={control.max} step={control.step} value={value} aria-label={`${control.label} slider`} onChange={(event) => set(Number(event.target.value))} />
    </div>
  );
}

function DragPlane({ x, y, vx, vy, set }: { x: Knob; y: Knob; vx: number; vy: number; set: (id: string, value: number) => void }) {
  const pad = useRef<HTMLDivElement | null>(null);
  function place(clientX: number, clientY: number) {
    const rect = pad.current?.getBoundingClientRect();
    if (!rect) return;
    const u = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    const v = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height));
    set(x.id, x.min + u * (x.max - x.min));
    set(y.id, y.min + v * (y.max - y.min));
  }
  const left = ((vx - x.min) / (x.max - x.min)) * 100;
  const top = ((vy - y.min) / (y.max - y.min)) * 100;
  return (
    <div className="liveart-choice" data-kind="drag">
      <span>{x.label} · {y.label}</span>
      <div
        className="liveart-plane"
        ref={pad}
        tabIndex={0}
        role="application"
        aria-label={`${x.label} y ${y.label}`}
        onPointerDown={(event) => {
          (event.currentTarget as HTMLDivElement).setPointerCapture(event.pointerId);
          place(event.clientX, event.clientY);
        }}
        onPointerMove={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) place(event.clientX, event.clientY);
        }}
        onKeyDown={(event) => {
          const stepX = event.key === "ArrowRight" ? x.step : event.key === "ArrowLeft" ? -x.step : 0;
          const stepY = event.key === "ArrowDown" ? y.step : event.key === "ArrowUp" ? -y.step : 0;
          if (!stepX && !stepY) return;
          event.preventDefault();
          if (stepX) set(x.id, Math.min(x.max, Math.max(x.min, vx + stepX)));
          if (stepY) set(y.id, Math.min(y.max, Math.max(y.min, vy + stepY)));
        }}
      >
        <i style={{ left: `${left}%`, top: `${top}%` }} />
      </div>
    </div>
  );
}

function Controls({ controls, vals, set }: { controls: Knob[]; set: (id: string, value: number) => void; vals: Record<string, number> }) {
  const drags = controls.filter((control) => kindOf(control) === "drag");
  const pair = drags.length >= 2 ? drags.slice(0, 2) : [];
  const paired = new Set(pair.map((control) => control.id));
  return (
    <div className="liveart-controls">
      {pair.length === 2 ? <DragPlane x={pair[0]} y={pair[1]} vx={vals[pair[0].id]} vy={vals[pair[1].id]} set={set} /> : null}
      {controls.map((control) => paired.has(control.id) ? (
        <label key={control.id} className="liveart-fallback-range">
          <span>{control.label}</span>
          <strong>{vals[control.id].toFixed(decimals(control.step))}</strong>
          <input type="range" min={control.min} max={control.max} step={control.step} value={vals[control.id]} aria-label={`${control.label} slider`} onChange={(event) => set(control.id, Number(event.target.value))} />
        </label>
      ) : (
        <Control key={control.id} control={control} value={vals[control.id]} set={(value) => set(control.id, value)} />
      ))}
    </div>
  );
}

function Anchor({ widget }: { widget: Noted }) {
  if (!widget.equation && !widget.anchor) return null;
  return (
    <div className="liveart-anchor">
      {widget.equation ? <Tex tex={widget.equation} display /> : null}
      {widget.anchor ? <p>“{widget.anchor}”</p> : null}
      {widget.cite ? <p className="liveart-cite">{widget.cite}</p> : null}
    </div>
  );
}

function Stage({ entry }: { entry: (typeof CATALOG)[number] }) {
  const box = useRef<HTMLDivElement | null>(null);
  const api = useRef<ReturnType<typeof mountSandbox> | null>(null);
  const { widget } = entry;
  const [vals, setVals] = useState<Record<string, number>>(() => Object.fromEntries(widget.controls.map((control) => [control.id, control.value])));
  const [down, setDown] = useState<string[] | null>(null);
  const wide = widget as unknown as Wide;
  const v04 = V04_ON && wide.version === VERSION_04;
  const [frame, setFrame] = useState<Frame>(null);

  useEffect(() => {
    if (down) return;
    const host = box.current;
    if (!host) return;
    let live = true;
    const handle = mountSandbox(host, widget, {
      v04: V04_ON,
      onStatus(next: { ok: boolean; reasons: string[] }) {
        if (live && !next.ok) setDown(next.reasons);
      },
      onFrame(next: Frame) {
        if (live) setFrame(next);
      },
      onSet(cid: string, value: number) {
        if (live) setVals((prev) => ({ ...prev, [cid]: value }));
      },
    });
    api.current = handle;
    return () => {
      live = false;
      handle.destroy();
    };
  }, [widget, down]);

  return (
    <article className="liveart-card" data-widget={widget.id} data-down={down ? "1" : "0"}>
      <p className="liveart-kicker">{kicker(entry.source)} · illustrative</p>
      <h2>{v04 ? wide.hook || widget.title : widget.title}</h2>
      {v04 && !down ? (
        <div className="liveart-head">
          {wide.legend && wide.legend.length ? (
            <p className="liveart-legend">
              {wide.legend.map((g) => <span key={g.text} data-color={g.color}><i />{g.text}</span>)}
            </p>
          ) : null}
          <dl className="liveart-reads">
            {(wide.readouts || []).filter((r) => r.show !== false && frame && r.id in frame.readouts).map((r) => (
              <div key={r.id} data-color={r.color || "ink"}><dt>{r.label}</dt><dd>{frame ? fmtRead(r, frame.readouts[r.id]) : ""}</dd></div>
            ))}
          </dl>
        </div>
      ) : null}
      <div className={down ? "liveart-stage is-static" : v04 ? "liveart-stage is-v04" : "liveart-stage"}>
        {down ? (
          <div key="static" className="liveart-static" data-reasons={down.join(" ")} role="note">
            <p className="liveart-kicker">Static explanation</p>
            <p className="liveart-explain">{widget.explain}</p>
            <ul>
              {widget.questions.map((item) => <li key={item.q}>{item.q}</li>)}
            </ul>
            <p className="liveart-reason">{fallbackText(down)}</p>
          </div>
        ) : (
          <div key="host" className="liveart-host" ref={box} />
        )}
      </div>
      {down ? null : (
        <Controls
          controls={widget.controls as Knob[]}
          vals={vals}
          set={(id, value) => {
            setVals((prev) => ({ ...prev, [id]: value }));
            api.current?.set(id, value);
          }}
        />
      )}
      {v04 && !down ? <p className="liveart-take" aria-live="polite">{takeawayText(wide, frame, vals)}</p> : null}
      {v04 && !down && frame && frame.cmarks.length ? (
        <p className="liveart-marks">{frame.cmarks.map((m) => <span key={m.control + m.label}>{m.control}: {m.label} · {m.value.toFixed(2)}</span>)}</p>
      ) : null}
      {down ? null : <Anchor widget={noted(wide)} />}
      {down ? null : <p className="liveart-explain">{widget.explain}</p>}
      {down ? null : (
        <ul>
          {widget.questions.map((item) => <li key={item.q}>{item.q}</li>)}
        </ul>
      )}
    </article>
  );
}

export default function LiveArtPage() {
  const [id, setId] = useState(CATALOG[0].widget.id);
  if (!liveOn()) {
    return (
      <main className="liveart">
        <p className="liveart-off">Live artifacts are off. Set NEXT_PUBLIC_RRM_LIVE_ARTIFACTS=1 to open the sandbox gallery.</p>
      </main>
    );
  }
  const entry = CATALOG.find((item) => item.widget.id === id) || CATALOG[0];
  return (
    <main className="liveart">
      <header>
        <p className="liveart-kicker">{VERSION} · sandboxed · no network</p>
        <h1>Live artifacts</h1>
        <p className="liveart-lead">Fifteen topics, each redrawn for this round. Nothing here is a measurement from a paper.</p>
      </header>
      <Stage key={entry.widget.id} entry={entry} />
      <nav className="liveart-nav" aria-label="Widgets">
        {CATALOG.map((item) => (
          <button key={item.widget.id} type="button" aria-pressed={item.widget.id === entry.widget.id} onClick={() => setId(item.widget.id)}>
            {item.widget.title}
          </button>
        ))}
      </nav>
    </main>
  );
}
