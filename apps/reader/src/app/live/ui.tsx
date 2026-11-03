"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { FEWSHOTS, WIDGETS } from "@/live/catalog";
import { CONTRACT_VERSION } from "@/live/contract";
import { mountIn } from "@/live/run";

export function Gallery() {
  const topics = useMemo(() => ["all", ...Array.from(new Set(WIDGETS.map((item) => item.topic)))], []);
  const [topic, setTopic] = useState("all");
  const [id, setId] = useState(FEWSHOTS[0].id);
  const host = useRef<HTMLDivElement | null>(null);
  const handle = useRef<{ set: (name: string, value: number) => void; destroy: () => void } | null>(null);
  const [specs, setSpecs] = useState<{ id: string; label: string; min: number; max: number; value: number; step: number }[]>([]);
  const [vals, setVals] = useState<Record<string, number>>({});
  const widget = WIDGETS.find((item) => item.id === id) || WIDGETS[0];
  const shown = WIDGETS.filter((item) => topic === "all" || item.topic === topic);

  useEffect(() => {
    if (!host.current) return;
    handle.current?.destroy();
    const mounted = mountIn(host.current, widget);
    handle.current = mounted;
    setSpecs(mounted.specs);
    setVals(Object.fromEntries(mounted.specs.map((spec) => [spec.id, spec.value])));
    return () => mounted.destroy();
  }, [widget]);

  return (
    <main className="live-page">
      <div className="live-wrap">
        <p className="live-kicker">{CONTRACT_VERSION} · illustrative</p>
        <h1>Live artifact mockups</h1>
        <p className="live-lead">
          {WIDGETS.length} hand-written draws in the Muse contract. {FEWSHOTS.length} primaries, one per topic.
          Moving a control is the explanation. These are not measurements from the papers.
        </p>
        <section className="live-stage" data-widget={widget.id}>
          <div ref={host} />
          <div>
            <p className="live-meta">{widget.topic} · {widget.id}</p>
            <p className="live-claim">{widget.title}</p>
            <p className="live-claim">{widget.explain}</p>
            <ul className="live-qs">
              {widget.questions.map((item) => <li key={item.q}>{item.q}</li>)}
            </ul>
            {specs.map((spec) => (
              <label className="live-ctrl" key={spec.id}>
                {spec.label}: {Number(vals[spec.id]).toFixed(2).replace(/\.00$/, "")}
                <input
                  type="range"
                  min={spec.min}
                  max={spec.max}
                  step={spec.step}
                  value={vals[spec.id] ?? spec.value}
                  aria-label={spec.label}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    setVals((prev) => ({ ...prev, [spec.id]: value }));
                    handle.current?.set(spec.id, value);
                  }}
                />
              </label>
            ))}
          </div>
        </section>
        <div className="live-filters">
          {topics.map((item) => (
            <button key={item} type="button" aria-pressed={topic === item} onClick={() => setTopic(item)}>
              {item === "all" ? "all" : item}
            </button>
          ))}
        </div>
        <div className="live-grid">
          {shown.map((item) => (
            <button key={item.id} type="button" className={item.id === widget.id ? "live-card is-on" : "live-card"} onClick={() => setId(item.id)}>
              <b>{item.id}</b>
              <span>{item.topic}</span>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
