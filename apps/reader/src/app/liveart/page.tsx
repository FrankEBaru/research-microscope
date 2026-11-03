"use client";

import { useEffect, useRef, useState } from "react";
import { fallbackText } from "@/lib/liveart/fallback.js";
import { mountSandbox } from "@/lib/liveart/mount.js";
import { ROUND } from "@/lib/liveart/round.js";
import { VERSION, liveOn } from "@/lib/liveart/spec.js";
import "@/styles/liveart.css";

const CATALOG = ROUND;

function kicker(source: string) {
  if (source === "round") return "Quality round";
  return "Current figure";
}

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
  const [down, setDown] = useState<string[] | null>(null);

  useEffect(() => {
    if (down) return;
    const host = box.current;
    if (!host) return;
    let live = true;
    const handle = mountSandbox(host, widget, {
      onStatus(next) {
        if (live && !next.ok) setDown(next.reasons);
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
      <h2>{widget.title}</h2>
      <div className={down ? "liveart-stage is-static" : "liveart-stage"}>
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
      )}
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
        <p className="liveart-lead">Fifteen topics. Ten are redrawn for this round. Five keep the current figure until their redraw lands. Nothing here is a measurement from a paper.</p>
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
