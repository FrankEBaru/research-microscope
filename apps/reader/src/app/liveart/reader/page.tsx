"use client";
// RRM-96 · Sample reader page: a B.1 paper section with its real text and equation, and the live-figure hook
// in the margin next to the claim it explains. Only widgets that passed the verifier and the sandbox are in the
// bundle (scripts/liveart_bundle.py). Paper.tsx is not used here on purpose (RRM-95 owns it); the markup reuses
// the reader's B.1 classes so the hook sits where it will sit in the real paper.
import { Fragment, useEffect, useMemo, useState } from "react";
import Margin from "@/components/paper/Margin";
import LiveHook from "@/components/liveart/LiveHook";
import { loadBundle, type LiveEntry } from "@/lib/liveart/live96";
import { Rich, Tex } from "@/lib/math";
import "@/styles/lectura.css";
import "@/styles/inicio.css";
import "@/styles/liveart-b1.css";

function Para({ text, claim }: { text: string; claim?: boolean }) {
  const parts = text.split(/\[\[|\]\]/);
  return (
    <p id={claim ? "lv96-claim" : undefined}>
      {parts.map((t, i) => (i % 2 ? <mark key={i} className="lv96-mark"><Rich text={t} /></mark> : <Fragment key={i}><Rich text={t} /></Fragment>))}
    </p>
  );
}

function Section({ entry }: { entry: LiveEntry }) {
  const p = entry.passage;
  const blocks = p?.blocks || [];
  return (
    <>
      <h3 data-toc>{entry.meta.section ? <span className="no">{entry.meta.section}</span> : null}{p?.heading || entry.meta.section_title}</h3>
      {blocks.map((b, i) => (
        <Fragment key={i}>
          {b.eq ? (
            <div className="eq blk"><Tex tex={b.eq + (b.no ? `\\tag{${b.no}}` : "")} display /></div>
          ) : (
            <Para text={b.p || ""} claim={b.claim} />
          )}
          {b.claim ? <div className="margin-inline"><LiveHook entry={entry} inline /></div> : null}
        </Fragment>
      ))}
    </>
  );
}

export default function LiveReaderPage() {
  const [entries, setEntries] = useState<LiveEntry[] | null>(null);
  const [err, setErr] = useState("");
  const [id, setId] = useState("");
  useEffect(() => {
    loadBundle().then((e) => {
      setEntries(e);
      const want = new URLSearchParams(window.location.search).get("w");
      setId(want && e.some((x) => x.id === want) ? want : e[0]?.id || "");
    }).catch((x) => setErr(String(x)));
  }, []);
  const entry = useMemo(() => entries?.find((e) => e.id === id) || null, [entries, id]);
  const pick = (next: string) => {
    setId(next);
    const u = new URL(window.location.href);
    u.searchParams.set("w", next);
    window.history.replaceState(null, "", u);
    window.scrollTo({ top: 0 });
  };

  if (err) return <main className="liveart"><p className="liveart-off">No live-figure bundle here ({err}). Build it with scripts/liveart_bundle.py.</p></main>;
  if (!entries) return null;
  if (!entry) return <main className="liveart"><p className="liveart-off">The bundle has no verified live figure.</p></main>;
  const m = entry.meta;
  return (
    <>
      <header className="b1-top">
        <div className="top-brand">
          <a className="wm" href="#" aria-label="Reading Microscope"><span className="wm-mark" aria-hidden="true"><i /></span><span className="wm-name">Reading Microscope</span></a>
        </div>
        <nav className="crumbs" aria-label="Breadcrumb"><span className="cur" aria-current="page">{m.paper}</span></nav>
      </header>
      <div className="lvl" data-screen="paper">
        <div className="folio">
          <nav className="toc" aria-label="Live figures">
            <p className="cap">Live figures</p>
            <ol>
              {entries.map((e) => (
                <li key={e.id} className={e.id === entry.id ? "is-on" : undefined}>
                  <a href={`?w=${e.id}`} onClick={(ev) => { ev.preventDefault(); pick(e.id); }}>
                    <span className="n">{e.meta.year}</span><span className="t">{e.meta.paper.split(":")[0]}</span>
                  </a>
                </li>
              ))}
            </ol>
          </nav>
          <article className="art paper sec is-read" key={entry.id}>
            <header className="ah paper-head">
              <div className="ah-bar">
                <div className="ah-meta"><span className="tnum">arXiv {m.arxiv}</span><span className="tnum">{m.year}</span></div>
              </div>
              <h1>{m.paper}</h1>
              <p className="ah-auth">{m.authors}</p>
              <p className="ah-links"><a href={`https://arxiv.org/abs/${m.arxiv}`} target="_blank" rel="noreferrer">arXiv</a></p>
            </header>
            <Section entry={entry} />
            <footer className="paper-foot">
              <p>Text and equations are from arXiv:{m.arxiv} by the authors, converted from LaTeX. The live figure in the margin is generated, and marked as such.</p>
            </footer>
          </article>
          <Margin layoutKey={entry.id} notes={[{ id: `lv-${entry.id}`, anchor: "#lv96-claim", kind: "lv", body: <LiveHook entry={entry} /> }]} />
        </div>
      </div>
    </>
  );
}
