"use client";

import { useEffect, useRef, useState } from "react";
import { GOLD } from "@/lib/liveart/gold.js";
import { mountSandbox } from "@/lib/liveart/mount.js";
import { SHOWCASE } from "@/lib/liveart/showcase.js";
import { VERSION, liveOn } from "@/lib/liveart/spec.js";
import "@/styles/liveart.css";

const CATALOG = [
  ...SHOWCASE.map((item) => ({ ...item, kind: "figure" })),
  ...GOLD.map((widget) => ({ widget, claim: "", kind: "contract" })),
];

function decimals(step: number) {
  const text = String(step);
  const dot = text.indexOf(".");
  return dot < 0 ? 0 : text.length - dot - 1;
}

function Stage({ entry }: { entry: (typeof CATALOG)[number] }) {
  const box = useRef<HTMLDivElement | null>(null);
  const api = useRef<ReturnType<typeof mountSandbox> | null>(null);
  const { widget } = entry;
  const [vals, setVals] = useState<Record<string, number>>(() => Object.fromEntries(widget.controls.map((control) => [control.id, control.value])));

  useEffect(() => {
    if (!box.current) return;
    const handle = mountSandbox(box.current, widget, { claim: entry.claim });
    api.current = handle;
    return () => handle.destroy();
  }, [widget, entry.claim]);

  return (
    <article className="liveart-card" data-widget={widget.id}>
      <p className="liveart-kicker">{entry.kind === "figure" ? "Figure" : "Contract example"} · illustrative</p>
      <h2>{widget.title}</h2>
      <div className="liveart-stage" ref={box} />
      <div className="liveart-controls">
        {widget.controls.map((control) => (
          <label key={control.id}>
            <span>{control.label}</span>
            <strong>{vals[control.id].toFixed(decimals(control.step))}</strong>
            <input
              type="range"
              min={control.min}
              max={control.max}
              step={control.step}
              value={vals[control.id]}
              aria-label={control.label}
              onChange={(event) => {
                const value = Number(event.target.value);
                setVals((prev) => ({ ...prev, [control.id]: value }));
                api.current?.set(control.id, value);
              }}
            />
          </label>
        ))}
      </div>
      <p className="liveart-explain">{widget.explain}</p>
      <ul>
        {widget.questions.map((item) => <li key={item.q}>{item.q}</li>)}
      </ul>
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
        <p className="liveart-lead">Small figures for one idea. The sliders are the explanation. Nothing here is a measurement from a paper.</p>
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
