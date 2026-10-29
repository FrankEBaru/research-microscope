"use client";
import { useMemo, useState } from "react";
import { simulate, meanVar, scaled, histogram, softmax, meanMaxWeight, theoreticalVar } from "@/lib/instrument.js";
import { Tex, Rich } from "@/lib/math";
import { ProvChip } from "./Bits";

const DKS = [4, 16, 32, 64, 128, 256, 512, 1024];
const SIGMAS = [0.5, 1, 2, 4];
const fmt = (x: number, d = 1) => x.toFixed(d);

function Hist({ values, sd, label, tone }: { values: Float64Array; sd: number; label: string; tone: string }) {
  const R = 4 * sd, bins = 41, W = 360, H = 120;
  const h = histogram(values, bins, -R, R);
  const mx = Math.max(...h, 1);
  const bw = W / bins;
  return (
    <figure className="hist">
      <svg viewBox={`0 0 ${W} ${H + 26}`} role="img" aria-label={label}>
        {h.map((c, i) => {
          const hh = (c / mx) * H;
          return <rect key={i} className={`bar bar-${tone}`} x={i * bw + 0.6} width={bw - 1.2} y={H - hh} height={hh} rx="1.5" />;
        })}
        <line x1={W / 2} x2={W / 2} y1="0" y2={H} className="axis-mid" />
        {[-1, 1].map((s) => <line key={s} x1={W / 2 + (s * sd * W) / (2 * R)} x2={W / 2 + (s * sd * W) / (2 * R)} y1="0" y2={H} className="axis-sd" />)}
        <text x="2" y={H + 18} className="ax">−{fmt(R, R < 10 ? 1 : 0)}</text>
        <text x={W / 2} y={H + 18} textAnchor="middle" className="ax">0 (líneas: ±1 desv. est.)</text>
        <text x={W - 2} y={H + 18} textAnchor="end" className="ax">{fmt(R, R < 10 ? 1 : 0)}</text>
      </svg>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

function Weights({ w, label, tone }: { w: number[]; label: string; tone: string }) {
  return (
    <figure className="weights">
      <div className="wbars">
        {w.map((x, i) => (
          <div key={i} className="wcol" title={`posición ${i + 1}: ${(100 * x).toFixed(1)}%`}>
            <div className={`wbar bar-${tone}`} style={{ height: `${Math.max(2, x * 100)}%` }} />
          </div>
        ))}
      </div>
      <figcaption>{label} · peso máximo {(100 * Math.max(...w)).toFixed(0)}%</figcaption>
    </figure>
  );
}

export default function Instrument({ content, goTo }: { content: any; goTo: (blockId: string) => void }) {
  const [bet, setBet] = useState<null | "same" | "x2" | "x4" | "skip">(null);
  const [di, setDi] = useState(3);
  const [si, setSi] = useState(1);
  const dk = DKS[di], sigma2 = SIGMAS[si];
  const N = 3000;
  const dots = useMemo(() => simulate({ dk, sigma2, n: N, seed: 42 }), [dk, sigma2]);
  const sdots = useMemo(() => scaled(dots, dk), [dots, dk]);
  const mv = meanVar(dots), ms = meanVar(sdots);
  const theory = theoreticalVar(dk, sigma2);
  const maxU = useMemo(() => meanMaxWeight(dots, 8, 200, 7), [dots]);
  const maxS = useMemo(() => meanMaxWeight(sdots, 8, 200, 7), [sdots]);
  const ex = useMemo(() => Array.from(dots.slice(0, 8)), [dots]);
  const wU = softmax(ex), wS = softmax(ex.map((x) => x / Math.sqrt(dk)));
  const relErr = Math.abs(mv.variance - theory) / theory;
  const I = content.instrument;
  const sdBefore = Math.sqrt(64), sdAfter = Math.sqrt(256);
  const betText = { same: "se queda igual", x2: "se duplica (×2)", x4: "se cuadruplica (×4)" } as const;

  return (
    <aside className="instrument" aria-label="Instrumento: por qué se divide por la raíz de d_k">
      <header>
        <div className="inst-title">
          <span className="inst-kicker">Instrumento</span>
          <h3>Por qué se divide por <Tex tex={"\\sqrt{d_k}"} /></h3>
        </div>
        <div className="chips">
          <ProvChip kind="calculo" />
          <ProvChip kind="curado" text="contrato por aprobar" />
        </div>
      </header>

      <p className="inst-lead">
        El paper afirma que <button className="link" onClick={() => goTo(I.claim.anchor.blockId)}>q·k tiene media 0 y varianza <Tex tex="d_k" /></button>, bajo este supuesto:
        «<Rich text={I.supposes.quote} />» (nota al pie de §3.2.1). Aquí puedes verlo moverse.
      </p>

      {bet === null && (
        <div className="bet" role="group" aria-label="Apuesta opcional">
          <p><strong>Antes de verlo (opcional):</strong> si subes <Tex tex="d_k" /> de 64 a 256, ¿qué le pasa a la <em>desviación estándar</em> de q·k?</p>
          <div className="bet-buttons">
            <button onClick={() => setBet("same")}>Se queda igual</button>
            <button onClick={() => setBet("x2")}>Se duplica (×2)</button>
            <button onClick={() => setBet("x4")}>Se cuadruplica (×4)</button>
            <button className="ghost" onClick={() => setBet("skip")}>Saltar</button>
          </div>
        </div>
      )}
      {bet !== null && bet !== "skip" && (
        <p className={`bet-result ${bet === "x2" ? "ok" : "no"}`}>
          Apostaste que {betText[bet]}. Con la afirmación del paper, la varianza pasa de 64 a 256 (×4), así que la desviación estándar pasa de {sdBefore} a {sdAfter} (×2).{" "}
          {bet === "x2" ? "Coincide con tu apuesta." : "No coincide con tu apuesta; el deslizador de abajo te deja comprobarlo."}
        </p>
      )}

      <div className="controls">
        <label>
          <span><Tex tex="d_k" /> = <strong>{dk}</strong>{dk === 64 && <em className="hint"> valor del paper (§3.2.2)</em>}</span>
          <input type="range" min={0} max={DKS.length - 1} step={1} value={di} onChange={(e) => setDi(+e.target.value)} aria-label="d_k" />
        </label>
        <label>
          <span>varianza de cada componente <Tex tex="\sigma^2" /> = <strong>{sigma2}</strong>{sigma2 === 1 && <em className="hint"> supuesto del paper</em>}</span>
          <input type="range" min={0} max={SIGMAS.length - 1} step={1} value={si} onChange={(e) => setSi(+e.target.value)} aria-label="sigma cuadrado" />
        </label>
      </div>

      <div className="hists">
        <Hist values={dots} sd={Math.sqrt(theory)} tone="a" label={`q·k sin escalar · desv. est. medida ${fmt(Math.sqrt(mv.variance), 2)}`} />
        <Hist values={sdots} sd={Math.sqrt(theory / dk)} tone="b" label={`q·k / √d_k · desv. est. medida ${fmt(Math.sqrt(ms.variance), 2)}`} />
      </div>

      <div className="stats">
        <div><span>Var(q·k) medida</span><b>{fmt(mv.variance, 1)}</b><small>teoría σ⁴·d_k = {fmt(theory, 1)}</small></div>
        <div><span>Var(q·k/√d_k) medida</span><b>{fmt(ms.variance, 2)}</b><small>teoría σ⁴ = {fmt(sigma2 * sigma2, 2)}</small></div>
        <div className={relErr < 0.08 ? "good" : "warn"}><span>Comprobación en esta sesión</span><b>{relErr < 0.08 ? "coincide" : "revisar"}</b><small>{fmt(100 * relErr, 1)}% de diferencia, n = {N}</small></div>
      </div>

      {sigma2 !== 1 && (
        <p className="inst-warn">
          Con <Tex tex={`\\sigma^2=${sigma2}`} /> la varianza escalada deja de ser 1: dividir por √d_k solo normaliza cuando los componentes tienen varianza 1. Es parte del supuesto que declara el paper.
        </p>
      )}

      <div className="softmax-row">
        <Weights w={wU} tone="a" label="softmax sin escalar (8 logits de ejemplo)" />
        <Weights w={wS} tone="b" label="softmax con escala 1/√d_k (los mismos 8)" />
      </div>
      <p className="small">
        Peso máximo medio en 200 conjuntos de 8 logits: <b>{(100 * maxU).toFixed(0)}%</b> sin escalar frente a <b>{(100 * maxS).toFixed(0)}%</b> con escala. El instrumento muestra cuán concentrado queda el softmax; no calcula gradientes, que es lo que el paper sospecha que se vuelve minúsculo.
      </p>

      <footer>
        <p className="small"><strong>Qué es esto:</strong> una ilustración de una afirmación del paper bajo sus supuestos, no un resultado del paper. {I.distributionNote} Pasa 6 pruebas derivadas de §3.2.1 (<code>tests/instrument.test.mjs</code>, incluida la comparación con una reimplementación independiente en numpy).</p>
      </footer>
    </aside>
  );
}
