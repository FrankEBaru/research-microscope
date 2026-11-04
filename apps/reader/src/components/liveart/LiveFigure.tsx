"use client";
// RRM-96 · The live figure panel. It grows out of the margin hook, sits over the paper like the B.1 atlas,
// and closes with Esc or a click outside. Top: the claim it explains (KaTeX + source). Middle: canvas and
// controls. Bottom: readings, the live takeaway, the curiosity questions, the explanation, and provenance.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { mountSandbox } from "@/lib/liveart/mount.js";
import { Rich, Tex } from "@/lib/math";
import {
  cssColor, decimals, fmtControl, fmtRead, sectionCite, shortSha, takeawayParts, uiFont,
  type Frame, type Knob, type LiveEntry, type Question,
} from "@/lib/liveart/live96";

const REDUCED = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function Label({ c }: { c: Knob }) {
  return (
    <span className="lv96-cl">
      {c.tex ? <span className="lv96-cl-s"><Tex tex={c.tex} /></span> : null}
      <span className="lv96-cl-n">{c.label}</span>
    </span>
  );
}

function Slider({ c, v, set, marks }: { c: Knob; v: number; set: (v: number) => void; marks: NonNullable<Frame>["cmarks"] }) {
  const f = (x: number) => Math.min(1, Math.max(0, (x - c.min) / (c.max - c.min)));
  return (
    <div className="lv96-sl" style={{ ["--v" as string]: f(v) }}>
      <div className="lv96-row"><Label c={c} /><b className="lv96-val">{fmtControl(c, v)}</b></div>
      <div className="lv96-sl-t">
        <span className="lv96-track"><span className="lv96-fill" /></span>
        {marks.map((m) => (
          <span key={m.id} className="lv96-tick" style={{ left: `${f(m.value) * 100}%` }} title={m.label} />
        ))}
        <input type="range" min={c.min} max={c.max} step={c.step} value={v} aria-label={c.label} onChange={(e) => set(Number(e.target.value))} />
        <span className="lv96-thumb" />
      </div>
      <div className="lv96-sl-x">
        {marks.some((m) => f(m.value) < 0.18) ? null : <span className="lo">{c.min.toFixed(decimals(c.step))}</span>}
        {marks.map((m) => (
          <span key={m.id} className={`mk${f(m.value) < 0.18 ? " is-l" : f(m.value) > 0.82 ? " is-r" : ""}`} style={{ left: `${f(m.value) * 100}%` }}>{m.label}</span>
        ))}
        {marks.some((m) => f(m.value) > 0.82) ? null : <span className="hi">{c.max.toFixed(decimals(c.step))}</span>}
      </div>
    </div>
  );
}

function Control({ c, v, set, marks }: { c: Knob; v: number; set: (v: number) => void; marks: NonNullable<Frame>["cmarks"] }) {
  const kind = c.kind || "slider";
  if (kind === "toggle") {
    const on = v >= 0.5;
    return (
      <button type="button" role="switch" aria-checked={on} className="lv96-ct lv96-tg" onClick={() => set(on ? c.min : c.max)}>
        <Label c={c} /><span className="lv96-sw" aria-hidden="true" />
      </button>
    );
  }
  if (kind === "select" && c.options?.length) {
    return (
      <div className="lv96-ct">
        <div className="lv96-row"><Label c={c} /></div>
        <div className="lv96-seg" role="radiogroup" aria-label={c.label}>
          {c.options.map((o, i) => {
            const val = c.min + i * c.step;
            return <button key={o} type="button" role="radio" aria-checked={Math.abs(v - val) < 1e-9} onClick={() => set(val)}>{o}</button>;
          })}
        </div>
      </div>
    );
  }
  if (kind === "button") {
    const n = Math.round((c.max - c.min) / c.step);
    const k = Math.round((v - c.min) / c.step);
    return (
      <div className="lv96-ct">
        <div className="lv96-row">
          <Label c={c} />
          <span className="lv96-stp">
            <button type="button" className="lv96-ib" aria-label="Previous step" disabled={k <= 0} onClick={() => set(c.min + (k - 1) * c.step)}>‹</button>
            <span className="lv96-stp-k">{k}<span> / {n}</span></span>
            <button type="button" className="lv96-ib" aria-label="Next step" disabled={k >= n} onClick={() => set(c.min + (k + 1) * c.step)}>›</button>
          </span>
        </div>
      </div>
    );
  }
  return <Slider c={c} v={v} set={set} marks={marks} />;
}

// "Set dk to 64", "Raise lr to 0.08": the host can do it for the reader. Only ids and labels the widget declares.
export function questionMoves(q: Question, controls: Knob[]): Record<string, number> | null {
  if (q.set && Object.keys(q.set).length) return q.set;
  const out: Record<string, number> = {};
  const re = /\b(?:set|put|raise|lower|move|drag|push|slide|increase|decrease|bring|take|turn)\s+(?:the\s+)?([A-Za-z_][\w ]{0,28}?)\s+(?:up |down |back )?to\s+(-?\d+(?:\.\d+)?)/gi;
  for (const m of q.q.matchAll(re)) {
    const name = m[1].trim().toLowerCase();
    const c = controls.find((k) => k.id.toLowerCase() === name || k.label.toLowerCase() === name || k.label.toLowerCase().startsWith(name + " ") || name.endsWith(" " + k.id.toLowerCase()));
    const val = Number(m[2]);
    if (c && Number.isFinite(val) && val >= c.min - 1e-9 && val <= c.max + 1e-9) out[c.id] = val;
  }
  return Object.keys(out).length ? out : null;
}

export default function LiveFigure({ entry, from, onClose }: { entry: LiveEntry; from: DOMRect | null; onClose: () => void }) {
  const w = entry.widget;
  const panel = useRef<HTMLDivElement | null>(null);
  const box = useRef<HTMLDivElement | null>(null);
  const closeBtn = useRef<HTMLButtonElement | null>(null);
  const api = useRef<ReturnType<typeof mountSandbox> | null>(null);
  const init = () => Object.fromEntries(w.controls.map((c) => [c.id, c.value]));
  const [vals, setVals] = useState<Record<string, number>>(init);
  const [frame, setFrame] = useState<Frame>(null);
  const [down, setDown] = useState<string[] | null>(null);
  const [leaving, setLeaving] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  const close = useCallback(() => {
    if (leaving) return;
    setLeaving(true);
    window.setTimeout(onClose, REDUCED() ? 0 : 160);
  }, [leaving, onClose]);

  // Continuity: the panel starts at the hook's box and grows to its place (B.1 atlas, ≤ 200 ms).
  useLayoutEffect(() => {
    const el = panel.current;
    if (!el || !from || REDUCED()) return;
    const b = el.getBoundingClientRect();
    el.style.transformOrigin = "0 0";
    el.style.transform = `translate(${from.left - b.left}px, ${from.top - b.top}px) scale(${from.width / b.width}, ${from.height / b.height})`;
    el.style.opacity = "0.3";
    void el.offsetWidth;
    el.classList.add("is-anim");
    el.style.transform = "";
    el.style.opacity = "";
    const t = window.setTimeout(() => el.classList.remove("is-anim"), 220);
    return () => window.clearTimeout(t);
  }, [from]);

  useEffect(() => {
    document.documentElement.classList.add("lv96-open");
    const t = window.setTimeout(() => closeBtn.current?.focus(), 30);
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", key);
    return () => { window.clearTimeout(t); document.removeEventListener("keydown", key); document.documentElement.classList.remove("lv96-open"); };
  }, [close]);

  useEffect(() => {
    const host = box.current;
    if (!host || down) return;
    let live = true;
    let handle: ReturnType<typeof mountSandbox> | null = null;
    uiFont().then((font) => {
      if (!live) return;
      handle = mountSandbox(host, w, {
        v04: true,
        font: font || undefined,
        onStatus(s: { ok: boolean; reasons: string[] }) { if (live && !s.ok) setDown(s.reasons); },
        onFrame(f: Frame) { if (live) setFrame(f); },
        onSet(id: string, v: number) { if (live) setVals((p) => ({ ...p, [id]: v })); },
      });
      api.current = handle;
    });
    return () => { live = false; handle?.destroy(); api.current = null; };
  }, [w, down]);

  const set = (id: string, v: number) => {
    setVals((p) => ({ ...p, [id]: v }));
    api.current?.set(id, v);
  };
  const apply = (moves: Record<string, number>) => Object.entries(moves).forEach(([id, v]) => set(id, v));

  const marksFor = (id: string) => (frame?.cmarks || []).filter((m) => m.control === id);
  const take = takeawayParts(w, frame, vals);
  const reads = (w.readouts || []).filter((r) => r.show !== false);
  const cite = sectionCite(entry.meta);
  const verified = entry.verdict.verify === "pass" && entry.verdict.sandbox === "pass";

  return createPortal(
    <div className={`lv96-ovl${leaving ? " is-out" : ""}`} onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div ref={panel} className="lv96-panel" role="dialog" aria-modal="true" aria-labelledby={`lv96-h-${entry.id}`} data-widget={w.id}>
        <span className="lv96-grab" aria-hidden="true" />
        <header className="lv96-h">
          <p className="lv96-kick">
            <span className="lv96-live"><i aria-hidden="true" />Live figure</span>
            <span>{entry.meta.section ? `§${entry.meta.section} ${entry.meta.section_title}` : entry.meta.paper}</span>
          </p>
          <button ref={closeBtn} type="button" className="lv96-x" aria-label="Close live figure" onClick={close}>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" /></svg>
          </button>
          <h2 id={`lv96-h-${entry.id}`}>{w.hook || w.title}</h2>
        </header>

        <section className="lv96-anchor" aria-label="What this figure explains">
          {w.anchor?.latex ? <div className="lv96-eq"><Tex tex={w.anchor.latex} display />{entry.meta.eq && /^\d+$/.test(entry.meta.eq) ? <span className="lv96-eqn">({entry.meta.eq})</span> : null}</div> : null}
          {w.anchor?.quote ? <blockquote className="lv96-quote">“<Rich text={w.anchor.quote} />”</blockquote> : null}
          <p className="lv96-src"><span className="pv"><b aria-hidden="true">“</b><span>{entry.meta.paper}</span></span><span className="lv96-dot">{cite}</span></p>
        </section>

        <div className="lv96-mid">
          <figure className="lv96-fig">
            {w.legend?.length ? (
              <figcaption className="lv96-lg">
                {w.legend.map((g) => <span key={g.text}><i className={`is-${g.kind || "line"}`} style={{ ["--c" as string]: cssColor(g.color) }} />{g.text}</span>)}
              </figcaption>
            ) : null}
            <div className="lv96-stage">
              {down ? (
                <div className="lv96-down" role="note">
                  <p>{w.explain}</p>
                  <p className="lv96-why">This figure did not mount here ({down.join(", ")}). The explanation stays.</p>
                </div>
              ) : <div className="lv96-host" ref={box} />}
            </div>
          </figure>
          <div className="lv96-ctrls">
            {w.controls.map((c) => <Control key={c.id} c={c} v={vals[c.id]} set={(v) => set(c.id, v)} marks={marksFor(c.id)} />)}
            <button type="button" className="lv96-reset" onClick={() => apply(init())}>Reset</button>
          </div>
        </div>

        <section className="lv96-out" aria-live="polite">
          {reads.length ? (
            <dl className="lv96-reads">
              {reads.map((r) => (
                <div key={r.id} style={{ ["--c" as string]: cssColor(r.color) }}>
                  <dt>{r.label}</dt>
                  <dd>{frame && r.id in frame.readouts ? fmtRead(r, frame.readouts[r.id]) : "—"}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {take.length ? (
            <p className="lv96-take">
              {take.map((p, i) => (p.id ? <b key={i} style={{ ["--c" as string]: cssColor(p.color) }}>{p.text}</b> : <span key={i}>{p.text}</span>))}
            </p>
          ) : null}
        </section>

        <div className="lv96-low">
          <section className="lv96-qs" aria-label="Curiosity questions">
            <h3>Try it</h3>
            <ol>
              {w.questions.map((q, i) => {
                const moves = questionMoves(q, w.controls);
                const isOpen = open === i;
                return (
                  <li key={q.q} className={isOpen ? "is-open" : undefined}>
                    <button type="button" className="lv96-q" aria-expanded={isOpen} onClick={() => { setOpen(isOpen ? null : i); if (!isOpen && moves) apply(moves); }}>
                      <span className="n">{i + 1}</span><span className="t">{q.q}</span>
                      {moves ? <span className="go" aria-hidden="true">Show me</span> : null}
                    </button>
                    {isOpen && q.why ? <p className="lv96-a">{q.why}</p> : null}
                  </li>
                );
              })}
            </ol>
          </section>
          <section className="lv96-ex" aria-label="Explanation">
            <h3>What you are seeing</h3>
            <p>{w.explain}</p>
          </section>
        </div>

        <footer className="lv96-prov">
          <span className="lv96-seal" data-ok={verified ? "1" : "0"}>
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5l5 2v4.2c0 3-2.1 5.6-5 6.8-2.9-1.2-5-3.8-5-6.8V3.5z" /><path d="M5.6 8.1l1.7 1.7 3.2-3.4" /></svg>
          </span>
          <span>
            Generated by <b>{entry.provenance.model}</b> · verified by <b>{entry.provenance.contract}</b> {verified ? "· sandbox passed" : ""} · id <code>{w.id}</code> <code>{shortSha(entry.provenance.sha)}</code>
          </span>
          <span className="lv96-prov-r">The figure is an illustration computed in your browser, not a result from the paper.</span>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
