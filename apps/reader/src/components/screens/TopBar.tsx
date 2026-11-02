"use client";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import "@/styles/inicio.css";
import { Cap, Icon } from "../ui";

type Step = { n: number; label: string; sub?: string; on?: () => void };

export type Crumb = {
  question: string;
  onAtlas: () => void;
  group?: { n: number; name: string } | null;
  paper?: string;
};

export default function TopBar({ core, live, liveOn, liveId, steps, level, draft, setDraft, onSearch, companion, setCompanion, onHome, crumb, back }: {
  core: boolean;
  live: boolean;
  liveOn: boolean;
  liveId: string;
  steps: Step[];
  level: number;
  draft: string;
  setDraft: (value: string) => void;
  onSearch: (e: FormEvent) => void;
  companion: boolean;
  setCompanion: (fn: (v: boolean) => boolean) => void;
  onHome?: () => void;
  crumb?: Crumb | null;
  back?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [shortcut, setShortcut] = useState("Ctrl+K");
  const barSearch = Boolean(core && live && (liveOn || liveId));
  const offline = process.env.NEXT_PUBLIC_RRM_OFFLINE === "1";

  useEffect(() => {
    const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
    const platform = nav.userAgentData?.platform || navigator.platform || "";
    setShortcut(/mac/i.test(platform) ? "⌘K" : "Ctrl+K");
  }, []);

  useEffect(() => {
    if (!core) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) {
        e.preventDefault();
        setOpen(false);
        return;
      }
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.key.toLowerCase() !== "k") return;
      e.preventDefault();
      const ask = document.getElementById("rrm-ask");
      if (ask) {
        ask.focus();
        return;
      }
      setOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [core, open]);

  useEffect(() => {
    if (open) document.getElementById("rrm-bar-q")?.focus();
  }, [open]);

  if (!core) {
    return (
      <header className="topbar">
        <a className="brand" href="#/" onClick={() => window.scrollTo({ top: 0 })}><span className="lens" aria-hidden="true" />Microscopio de lectura</a>
        {!(core && (liveOn || liveId)) && (
          <nav className="scope" aria-label="Nivel de zoom">
            {steps.map((s) => (
              <button key={s.n} className={`step ${level === s.n ? "on" : ""} ${level > s.n ? "past" : ""}`} disabled={!s.on || level === s.n} onClick={s.on} title={s.sub || ""}>
                <span className="dot">{s.n}</span><span className="lbl">{s.label}</span>
              </button>
            ))}
          </nav>
        )}
        {live && !(core && !liveOn && !liveId) && (
          <form className="live-search" onSubmit={onSearch}>
            <input aria-label="Pregunta" title={draft || undefined} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Pregunta" />
            <button type="submit">Buscar</button>
          </form>
        )}
        {!core && <button className="companion-toggle" aria-pressed={companion} onClick={() => setCompanion((v) => !v)} title="Compañero de lectura opcional: ofrece ayuda, nunca interrumpe, no guarda nada (tecla C)">Compañero {companion ? "activado" : "apagado"}</button>}
        {!(live && process.env.NEXT_PUBLIC_RRM_OFFLINE !== "1") && <span className="proto">prototipo · datos locales</span>}
      </header>
    );
  }

  const focusAsk = () => {
    const ask = document.getElementById("rrm-ask");
    if (ask) ask.focus();
    else setOpen(true);
  };

  return (
    <header className="b1-top">
      <div className="top-brand">
        {back}
        <a className="wm" href="#/" aria-label="Reading Microscope, home" onClick={(e) => { e.preventDefault(); onHome ? onHome() : window.scrollTo({ top: 0 }); }}>
          <span className="wm-mark" aria-hidden="true"><i /></span>
          <span className="wm-name">Reading Microscope</span>
        </a>
      </div>
      <nav className="crumbs" aria-label="Breadcrumb">
        {crumb?.question && (
          <>
            {crumb.paper
              ? <button type="button" onClick={crumb.onAtlas}>{crumb.question}</button>
              : <span className="cur" aria-current="page">{crumb.question}</span>}
            {crumb.group && crumb.paper && (
              <>
                <span className="sep" aria-hidden="true">/</span>
                <span className="cur">
                  <i className="dot" style={{ ["--c" as string]: `var(--grp-${crumb.group.n})` }} aria-hidden="true" />
                  {crumb.group.name}
                </span>
              </>
            )}
            {crumb.paper && (
              <>
                <span className="sep" aria-hidden="true">/</span>
                <span className="cur" aria-current="page">{crumb.paper}</span>
              </>
            )}
          </>
        )}
      </nav>
      <div className="top-tools">
        {offline && <Cap>local data</Cap>}
        {barSearch ? (
          <form className={`live-search b1-search ${open ? "is-open" : ""}`} onSubmit={onSearch}>
            <button type="button" className="b1-search-hit press" aria-label="Search" onClick={focusAsk}>
              <Icon name="search" size={18} />
              {!open && <span className="b1-search-label">Search</span>}
            </button>
            {!open && <kbd aria-hidden="true">{shortcut}</kbd>}
            {open && (
              <input
                id="rrm-bar-q"
                aria-label="Pregunta"
                title={draft || undefined}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Search"
                onBlur={(e) => {
                  if (e.currentTarget.form?.contains(e.relatedTarget as Node)) return;
                  if (!draft.trim()) setOpen(false);
                }}
              />
            )}
          </form>
        ) : (
          <button type="button" className="b1-search press" aria-label="Search" onClick={focusAsk}>
            <Icon name="search" size={18} />
            <span className="b1-search-label">Search</span>
            <kbd>{shortcut}</kbd>
          </button>
        )}
      </div>
    </header>
  );
}
