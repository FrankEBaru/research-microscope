import { Prov } from "@/lib/types";

const LABEL: Record<Prov, string> = {
  paper: "del paper",
  curado: "curado a mano",
  simulado: "ejemplo simulado",
  calculo: "cálculo bajo los supuestos del paper",
  hipotesis: "idea en prueba: aún sin evidencia de que ayude",
};

export function ProvChip({ kind, text, title }: { kind: Prov; text?: string; title?: string }) {
  return <span className={`chip chip-${kind}`} title={title ?? LABEL[kind]}>{text ?? LABEL[kind]}</span>;
}

export function Coverage({ have, total }: { have: number; total: number }) {
  return (
    <div className="coverage" title="Papers de este cluster de los que se leyó el texto completo (el resto: solo abstract)">
      <div className="coverage-bar"><div style={{ width: `${(100 * have) / total}%` }} /></div>
      <span>texto completo de {have} de {total}</span>
    </div>
  );
}
