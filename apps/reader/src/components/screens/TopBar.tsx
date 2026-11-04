"use client";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import "@/styles/inicio.css";
import { Cap, Icon } from "../ui";
import { Rich } from "@/lib/math";
import BrandMark from "../BrandMark";

type Step = { n: number; label: string; sub?: string; on?: () => void };

export type Crumb = {
  question: string;
  onAtlas: () => void;
  onGroup?: () => void;
  group?: { id?: string; n: number; name: string } | null;
  paper?: string;
  paperId?: string;
  steps?: { id: string; title: string }[];
  onStep?: (id: string) => void;
};

export default function TopBar({ core, live, liveOn, liveId, steps, level, draft, setDraft, onSearch, companion, setCompanion, onHome, crumb, back, recorded = [] }: {
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
  recorded?: string[];
}) {
  const [open, setOpen] = useState(false);
  const [shortcut, setShortcut] = useState("Ctrl+K");
  // RRM-97: the server and the first client render draw the same top-tools (plain search button).
  // Route, live state and the offline tag only show after mount, so hydration never depends on them.
  const [mounted, setMounted] = useState(false);
  const barSearch = mounted && Boolean(core && live && (liveOn || liveId));
  const offline = mounted && process.env.NEXT_PUBLIC_RRM_OFFLINE === "1";

  useEffect(() => {
    setMounted(true);
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
        <a className="brand" href="#/" onClick={() => window.scrollTo({ top: 0 })}><BrandMark size={20} />Reading Microscope</a>
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
            <input aria-label="Question" title={draft || undefined} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Question" list={recorded.length ? "rrm-recorded" : undefined} />
            <button type="submit">Search</button>
          </form>
        )}
        {!core && <button className="companion-toggle" aria-pressed={companion} onClick={() => setCompanion((v) => !v)} title="Optional reading companion: offers help, never interrupts, stores nothing (C key)">Companion {companion ? "on" : "off"}</button>}
        {!(live && process.env.NEXT_PUBLIC_RRM_OFFLINE !== "1") && <span className="proto">prototype · local data</span>}
        {recorded.length > 0 && (
          <datalist id="rrm-recorded">
            {recorded.map((q) => <option key={q} value={q} />)}
          </datalist>
        )}
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
          <BrandMark />
          <span className="wm-name">Reading Microscope</span>
        </a>
      </div>
      <nav className="crumbs" aria-label="Breadcrumb">
        {crumb?.question && (
          <>
            {crumb.paper || (crumb.steps && crumb.steps.length)
              ? <button type="button" onClick={crumb.onAtlas}>{crumb.question}</button>
              : <span className="cur" aria-current="page">{crumb.question}</span>}
            {crumb.group && crumb.paper && (
              <>
                <span className="sep" aria-hidden="true">/</span>
                <button type="button" onClick={crumb.onGroup || crumb.onAtlas}>
                  <i className="dot" style={{ ["--c" as string]: `var(--grp-${crumb.group.n})` }} aria-hidden="true" />
                  <Rich text={crumb.group.name} />
                </button>
              </>
            )}
            {(crumb.steps || []).filter((step) => step.id !== crumb.paperId).map((step) => (
              <span key={step.id} className="crumb-step">
                <span className="sep" aria-hidden="true">/</span>
                <button type="button" onClick={() => crumb.onStep?.(step.id)}><Rich text={step.title || step.id} /></button>
              </span>
            ))}
            {crumb.paper && (
              <>
                <span className="sep" aria-hidden="true">/</span>
                <span className="cur" aria-current="page"><Rich text={crumb.paper} /></span>
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
                aria-label="Question"
                title={draft || undefined}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Search"
                list={recorded.length ? "rrm-recorded" : undefined}
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
      {recorded.length > 0 && (
        <datalist id="rrm-recorded">
          {recorded.map((q) => <option key={q} value={q} />)}
        </datalist>
      )}
    </header>
  );
}
