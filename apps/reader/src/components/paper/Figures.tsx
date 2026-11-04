"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Paper } from "@/lib/types";
import { ProvChip } from "../Bits";
import { crops, figureCandidates, figureUrl, paperKey } from "@/lib/backend.js";
import { devBegin, devFinish } from "@/lib/devlog.js";
import { reportFault } from "@/lib/faults.js";
import { Icon } from "../ui";

/** Figura con zonas: cajas sobre la figura ORIGINAL (marcadas a mano) que enlazan cada parte con la frase del paper que la explica. */
export function ZoneFig({ paper, name, alt, zones, onGo }: { paper: Paper; name: string; alt: string; zones: any[]; onGo: (blockId: string) => void }) {
  const [on, setOn] = useState<string | null>(null);
  const z = zones.find((x) => x.id === on);
  return (
    <div className="zonefig">
      <div className="zone-box" onMouseLeave={() => setOn(null)}>
        <FigImg paper={paper} name={name} alt={alt} />
        {zones.map((x) => (
          <button key={x.id} className={`zone ${on === x.id ? "on" : ""}`} data-zone={x.id} aria-label={x.label} onMouseEnter={() => setOn(x.id)} onFocus={() => setOn(x.id)} onClick={() => setOn(x.id)}
            style={{ left: `${x.box[0] * 100}%`, top: `${x.box[1] * 100}%`, width: `${(x.box[2] - x.box[0]) * 100}%`, height: `${(x.box[3] - x.box[1]) * 100}%` }} />
        ))}
      </div>
      <div className="zone-card" role="status" aria-live="polite">
        {z ? (<><b>{z.label}</b><blockquote>«{z.quote}»</blockquote><button className="link" onClick={() => onGo(z.anchor.blockId)}>ver dónde lo dice →</button></>)
          : <span className="muted">Pasa el cursor por una parte de la figura para ver qué dice el paper de ella.</span>}
      </div>
      <div className="chips"><ProvChip kind="curado" text="zonas marcadas a mano, sin modelo; la figura no se modifica" /></div>
    </div>
  );
}

export function FigImg({ paper, name, alt, eager }: { paper: Paper; name: string; alt: string; eager?: boolean }) {
  const names = figureCandidates(name);
  const [idx, setIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const step = useRef(0);
  const src = names[idx] ? figureUrl(paperKey(paper), names[idx]) : "";
  const missing = paper.stage === "sections" || !src;
  useEffect(() => { setIdx(0); setLoaded(false); }, [name, paper.stage]);
  useEffect(() => {
    if (missing) return;
    step.current = devBegin("figura", names[idx] || name);
  }, [name, paper.stage, missing, src]);
  const spent = idx > 0 && idx >= names.length;
  useEffect(() => {
    if (spent) reportFault({ code: "F-FIG", where: "FigImg", detail: String(name) });
  }, [spent, name]);
  // RRM-47: si ningún nombre cargó (404), la figura se oculta sin hueco ni ícono roto.
  if (missing) return idx > 0 ? null : <div className="fig-missing">Figure not available</div>;
  return (
    <span className={`fig-slot ${loaded ? "in" : ""}`}>
      {!loaded && <span className="fig-ph">Figure</span>}
      <img
        src={src}
        alt={alt}
        loading={eager ? "eager" : "lazy"}
        decoding="async"
        fetchPriority={eager ? "high" : "low"}
        onLoad={() => { setLoaded(true); devFinish(step.current, "ok"); }}
        onError={() => {
          devFinish(step.current, "error", "no cargó");
          setLoaded(false);
          setIdx((n) => n + 1);
        }}
      />
    </span>
  );
}

/** La figura grande, en el mismo orden. Clic afuera o Escape la cierra. */
export function FigZoom({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fig-zoom" role="dialog" aria-modal="true" aria-label="Figure" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="fig-zoom-sheet" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="fig-zoom-x press" aria-label="Close" onClick={(e) => { e.stopPropagation(); onClose(); }}><Icon name="close" size={16} /></button>
        {children}
      </div>
    </div>
  );
}

export function CropStrip({ id }: { id: string }) {
  const [rows, setRows] = useState<{ page?: number; file?: string }[] | null>(null);
  useEffect(() => {
    let stop = false;
    crops(id, "0,1,2").then(
      (body: any) => { if (!stop) setRows(Array.isArray(body?.crops) ? body.crops : []); },
      () => { if (!stop) setRows([]); },
    );
    return () => { stop = true; };
  }, [id]);
  if (!rows?.length) return null;
  return (
    <section className="crops" aria-label="Recortes de página" data-crops>
      <p className="small">Recortes de las páginas grabadas</p>
      <div className="fig-imgs">{rows.map((row) => row.file ? <img key={row.file} src={figureUrl(id, row.file)} alt={`recorte, página ${row.page ?? ""}`} loading="lazy" decoding="async" onError={(e) => e.currentTarget.setAttribute("hidden", "")} /> : null)}</div>
    </section>
  );
}
