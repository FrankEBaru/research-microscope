import type { Prov as Kind } from "@/lib/types";

const LABEL: Record<Kind, string> = {
  paper: "del paper",
  curado: "curado a mano",
  simulado: "ejemplo simulado",
  calculo: "cálculo bajo los supuestos del paper",
  hipotesis: "idea en prueba: aún sin evidencia de que ayude",
};
const GLYPH: Record<Kind, string> = { paper: "“", curado: "◆", calculo: "ƒ", simulado: "∿", hipotesis: "∿" };

export function Prov({ kind, text, title }: { kind: Kind; text?: string; title?: string }) {
  const mod = kind === "simulado" || kind === "hipotesis" ? " pv--generated" : kind === "calculo" ? " pv--computed" : "";
  return (
    <span className={`pv${mod}`} title={title ?? LABEL[kind]}>
      <b aria-hidden="true">{GLYPH[kind]}</b>
      <span>{text ?? LABEL[kind]}</span>
    </span>
  );
}
