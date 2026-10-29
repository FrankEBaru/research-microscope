"use client";
import { useEffect, useState } from "react";

export interface Offer { key: string; text: string; accept: string; onAccept: () => void }

const INK = "#1d1b17";

/** Tardígrado («oso de agua»): vista lateral, cuatro patas romas, una mejilla. */
function Tardigrado() {
  return (
    <g className="ch-body">
      <g className="ch-legs" fill="#cfd9c9" stroke={INK} strokeWidth="2.6" strokeLinejoin="round">
        <rect x="19" y="49" width="9" height="11" rx="4.5" /><rect x="31" y="51" width="9" height="11" rx="4.5" /><rect x="45" y="51" width="9" height="11" rx="4.5" /><rect x="57" y="47" width="9" height="11" rx="4.5" />
      </g>
      <path d="M10 36 C10 18 28 9 46 11 C64 13 73 26 71 39 C69 52 54 56 38 56 C22 56 10 52 10 36 Z" fill="#dfe8d9" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
      <g stroke={INK} strokeOpacity=".22" strokeWidth="2" fill="none" strokeLinecap="round"><path d="M33 13 Q37 34 33 54" /><path d="M46 12 Q50 34 46 55" /><path d="M59 16 Q62 34 59 50" /></g>
      <ellipse cx="25" cy="40" rx="4.2" ry="3" fill="#efc7b4" opacity=".85" />
      <ellipse className="ch-eye" cx="21" cy="32" rx="2.6" ry="3.1" fill={INK} />
      <path d="M13 41 Q17 45 22 43" fill="none" stroke={INK} strokeWidth="2" strokeLinecap="round" />
    </g>
  );
}

/** Diatomea: concha de sílice con simetría radial y una cara mínima. */
function Diatomea() {
  const rays = Array.from({ length: 16 }, (_, i) => { const t = (i * Math.PI * 2) / 16; return <line key={i} x1={32 + Math.cos(t) * 13} y1={32 + Math.sin(t) * 13} x2={32 + Math.cos(t) * 25} y2={32 + Math.sin(t) * 25} />; });
  return (
    <g className="ch-body">
      <circle cx="32" cy="32" r="28" fill="#efe3c6" stroke={INK} strokeWidth="3" />
      <circle cx="32" cy="32" r="12" fill="#f8f1de" stroke={INK} strokeOpacity=".35" strokeWidth="1.6" />
      <g stroke={INK} strokeOpacity=".28" strokeWidth="1.8" strokeLinecap="round">{rays}</g>
      <circle cx="32" cy="32" r="21.5" fill="none" stroke={INK} strokeOpacity=".28" strokeWidth="1.6" strokeDasharray="1 4.2" strokeLinecap="round" />
      <g className="ch-eyes"><ellipse cx="27.4" cy="31" rx="1.9" ry="2.4" fill={INK} /><ellipse cx="36.6" cy="31" rx="1.9" ry="2.4" fill={INK} /></g>
      <path d="M28 37 Q32 40.4 36 37" fill="none" stroke={INK} strokeWidth="1.9" strokeLinecap="round" />
    </g>
  );
}

/** Volvox: colonia esférica con esferas hijas. */
function Volvox() {
  const kids = [[22, 22], [41, 20], [47, 36], [38, 47], [20, 43], [31, 33]] as const;
  return (
    <g className="ch-body">
      <circle cx="32" cy="32" r="28" fill="#dde8ec" fillOpacity=".75" stroke={INK} strokeWidth="3" />
      {kids.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === 5 ? 0 : 6} fill="#b9d3b0" stroke={INK} strokeOpacity=".55" strokeWidth="1.6" />)}
      <g className="ch-eyes"><ellipse cx="26" cy="31" rx="2" ry="2.5" fill={INK} /><ellipse cx="38" cy="31" rx="2" ry="2.5" fill={INK} /></g>
      <path d="M27 38 Q32 42 37 38" fill="none" stroke={INK} strokeWidth="2" strokeLinecap="round" />
      <path d="M14 14 Q18 9 24 8" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" opacity=".9" />
    </g>
  );
}

export const CHARACTERS = [
  { id: "tardigrado", name: "Tardígrado", vb: "0 0 80 64", el: <Tardigrado /> },
  { id: "diatomea", name: "Diatomea", vb: "0 0 64 64", el: <Diatomea /> },
  { id: "volvox", name: "Volvox", vb: "0 0 64 64", el: <Volvox /> },
];

function Character({ idx, wiggle }: { idx: number; wiggle: boolean }) {
  const c = CHARACTERS[idx % CHARACTERS.length];
  return <svg className={`char char-${c.id} ${wiggle ? "wiggle" : ""}`} width="68" height="68" viewBox={c.vb} role="img" aria-label={`Compañero de lectura: ${c.name}`}>{c.el}</svg>;
}

export default function Companion({ offer, onAnswer, onHide }: { offer: Offer | null; onAnswer: (accepted: boolean) => void; onHide: () => void }) {
  const [idx, setIdx] = useState(0); // personaje elegido: solo en memoria, como todo lo del compañero
  useEffect(() => {
    if (!offer) return;
    const t = setTimeout(() => onAnswer(false), 20000);          // sin respuesta: se retira sola, cuenta como descartada
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onAnswer(false); };
    window.addEventListener("keydown", k); return () => { clearTimeout(t); window.removeEventListener("keydown", k); };
  }, [offer]);
  return (
    <aside className="companion" aria-label="Compañero de lectura (opcional)">
      {offer && (
        <div className="c-bubble" role="status">
          <p>{offer.text}</p>
          <div className="c-actions">
            <button className="c-yes" onClick={() => { offer.onAccept(); onAnswer(true); }}>{offer.accept}</button>
            <button className="c-no" onClick={() => onAnswer(false)}>No, gracias</button>
          </div>
          <small>No guardo ni envío lo que haces: lo cuento solo en esta pestaña.</small>
        </div>
      )}
      <div className="c-row">
        <button className="c-swap" onClick={() => setIdx((i) => (i + 1) % CHARACTERS.length)} title="Cambiar de compañero" aria-label={`Cambiar de compañero (ahora: ${CHARACTERS[idx].name})`}>↻</button>
        <button className="c-avatar" onClick={onHide} title={`${CHARACTERS[idx].name} · clic para ocultar (tecla C)`} aria-label="Ocultar el compañero"><Character idx={idx} wiggle={!!offer} /></button>
      </div>
    </aside>
  );
}
