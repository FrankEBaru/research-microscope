"use client";
// RRM-95 · B.1 instrument "Why divide by √d_k?" for Attention Is All You Need (live + core).
// Same math as the curated one (lib/instrument.js, tested in tests/instrument.test.mjs);
// the B.1 layout: a bet, one slider, two histograms with fixed axes, one result, details folded.
import { useMemo, useState, type CSSProperties } from "react";
import { histogram, meanMaxWeight, meanVar, scaled, simulate, theoreticalVar } from "@/lib/instrument.js";
import { Tex, type Sym } from "@/lib/math";
import { Prov } from "../ui";
import "@/styles/instrument.css";

const DKS = [16, 32, 64, 128, 256, 512, 1024];
const N = 3000;
const BINS = 29;
const RAW = 96; // fixed axes: the spread you see growing is real, not a rescaled plot
const ON = 4;

/** The block right after which the instrument goes: "To counteract this effect, we scale the dot products by…". */
export function dkAnchor(paper: { arxivId?: string; corpusid?: any; blocks?: any[] }, plain: (inls: any[]) => string) {
  const isAttention = paper?.arxivId === "1706.03762" || String(paper?.corpusid ?? "") === "13756489";
  if (!isAttention) return "";
  const hit = (paper.blocks || []).find((b) => b.kind === "p" && /counteract this effect, we scale the dot products/i.test(plain(b.inlines || [])));
  return hit ? hit.id : "";
}

function Hist({ values, range, tone, label, sd }: { values: Float64Array; range: number; tone: "raw" | "on"; label: React.ReactNode; sd: number }) {
  const [hov, setHov] = useState<number | null>(null);
  const W = 360, H = 120, bw = W / BINS;
  const h = useMemo(() => histogram(values, BINS, -range, range), [values, range]);
  const mx = Math.max(...h, 1);
  const lo = (i: number) => -range + (i * 2 * range) / BINS;
  const sdx = (sd / range) * (W / 2);
  return (
    <figure className={`hist hist--${tone}`}>
      <figcaption><span className="h-lab">{label}</span><span className="h-sd tnum">spread {sd.toFixed(2)}</span></figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        aria-hidden="true"
        onPointerMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const i = Math.floor(((e.clientX - r.left) / r.width) * BINS);
          setHov(i >= 0 && i < BINS ? i : null);
        }}
        onPointerLeave={() => setHov(null)}
      >
        <line className="axl" x1="0" x2={W} y1={H - 0.5} y2={H - 0.5} />
        {h.map((c, i) => {
          const hh = Math.max(c ? 1.5 : 0, (c / mx) * (H - 8));
          return <rect key={i} className={hov === i ? "hov" : undefined} x={i * bw + 1.2} width={bw - 2.4} y={H - hh} height={hh} rx="2" />;
        })}
        {sdx < W / 2 ? [-1, 1].map((s) => <line key={s} className="sd" x1={W / 2 + s * sdx} x2={W / 2 + s * sdx} y1="0" y2={H} />) : null}
      </svg>
      <p className="h-ax tnum"><span>−{range}</span><span>0</span><span>{range}</span></p>
      {hov != null ? (
        <span className="tip tnum" style={{ left: `${((hov + 0.5) / BINS) * 100}%`, top: "26%" } as CSSProperties}>
          {lo(hov).toFixed(range > 10 ? 0 : 2)} to {lo(hov + 1).toFixed(range > 10 ? 0 : 2)} · {h[hov]}
        </span>
      ) : null}
    </figure>
  );
}

export default function DkInstrument({ syms = [] }: { syms?: Sym[] }) {
  const [bet, setBet] = useState<"" | "same" | "x2" | "x4" | "skip">("");
  const [di, setDi] = useState(2);
  const dk = DKS[di];
  const dots = useMemo(() => simulate({ dk, sigma2: 1, n: N, seed: 42 }), [dk]);
  const sdots = useMemo(() => scaled(dots, dk), [dots, dk]);
  const mv = meanVar(dots), ms = meanVar(sdots);
  const maxU = useMemo(() => meanMaxWeight(dots, 8, 200, 7), [dots]);
  const maxS = useMemo(() => meanMaxWeight(sdots, 8, 200, 7), [sdots]);
  const err = Math.abs(ms.variance - 1);
  const ok = err < 0.08;
  const T = (tex: string) => <Tex tex={tex} syms={syms} />;
  const picked = { same: "stays the same", x2: "doubles", x4: "quadruples" } as const;
  const v = di / (DKS.length - 1);

  return (
    <figure className="ins" aria-label="Instrument: why divide by the square root of d_k">
      <header className="ins-h">
        <h3>Why divide by {T("\\sqrt{d_k}")}?</h3>
        <p className="ins-pv"><Prov kind="calculo" text="computed here" /><Prov kind="simulado" text="simulated data" /></p>
      </header>

      <div className="bet">
        <p>If {T("d_k")} goes from 64 to 256, the spread of {T("q \\cdot k")}…</p>
        <div className="opts" role="group" aria-label="Your bet">
          {(["same", "x2", "x4"] as const).map((k) => (
            <button key={k} type="button" className={`opt press${bet === k ? " is-on" : ""}`} aria-pressed={bet === k} onClick={() => setBet(k)}>{picked[k]}</button>
          ))}
          <button type="button" className="skip" onClick={() => setBet("skip")}>skip</button>
        </div>
        {bet && bet !== "skip" ? (
          <p className="bet-r" aria-live="polite">You picked <b>{picked[bet]}</b>. Variance goes 64 → 256, so the spread goes 8 → 16: it doubles.</p>
        ) : null}
      </div>

      <div className="sl">
        <p className="sl-l"><span className="sl-s">{T("d_k")}</span><b className="tnum">{dk}</b>{dk === 64 ? <span className="sl-h">the paper’s value</span> : null}</p>
        <input
          className="sl-in"
          type="range"
          min={0}
          max={DKS.length - 1}
          step={1}
          value={di}
          onChange={(e) => setDi(+e.target.value)}
          aria-label="d_k"
          aria-valuetext={String(dk)}
          style={{ ["--v" as string]: String(v) } as CSSProperties}
        />
        <p className="sl-x tnum">{DKS.map((x) => <span key={x}>{x}</span>)}</p>
      </div>

      <div className="hists">
        <Hist values={dots} range={RAW} tone="raw" sd={Math.sqrt(mv.variance)} label={T("q \\cdot k")} />
        <Hist values={sdots} range={ON} tone="on" sd={Math.sqrt(ms.variance)} label={T("q \\cdot k \\,/ \\sqrt{d_k}")} />
      </div>

      <div className="result" aria-live="polite">
        <p className="res-v" aria-hidden="true">{ok ? "≈" : "≠"}</p>
        <p className="res-t">
          <b>{ok ? "Matches the paper" : "Off from the paper"}</b>
          <span className="tnum">variance {ms.variance.toFixed(2)} vs 1.00 · n = {N.toLocaleString("en-US")}</span>
        </p>
      </div>

      <details className="det">
        <summary>Details</summary>
        <p>
          Variance of {T("q \\cdot k")}: {mv.variance.toFixed(1)} measured, {theoreticalVar(dk, 1).toFixed(1)} in theory.
          Softmax of 8 example logits: max weight {(100 * maxU).toFixed(0)}% unscaled, {(100 * maxS).toFixed(0)}% scaled.
          Components drawn from a standard normal; the paper does not fix the distribution.
          Same code as the tested instrument (tests/instrument.test.mjs).
        </p>
      </details>
    </figure>
  );
}
