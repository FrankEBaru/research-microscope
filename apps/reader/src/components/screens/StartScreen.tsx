"use client";
import { useEffect, useState, type FormEvent } from "react";
import "@/styles/inicio.css";
import { readQuestions } from "@/lib/qcache.js";
import { Cap, Icon } from "../ui";
import BootPanel from "./BootPanel";

type SearchEvent = { preventDefault: () => void; query?: string };

export default function StartScreen({ draft, setDraft, onSearch, pending, engine, phase, recorded = [] }: {
  draft: string;
  setDraft: (value: string) => void;
  onSearch: (e: SearchEvent) => void;
  pending: boolean;
  engine: string;
  phase: string;
  recorded?: string[];
}) {
  const [recent, setRecent] = useState<string[]>([]);
  useEffect(() => {
    try {
      const rows = readQuestions(localStorage);
      setRecent(rows.map((row: { q?: string }) => String(row?.q || "")).filter(Boolean).slice(0, 3));
    } catch {
      setRecent([]);
    }
  }, []);
  const needle = draft.trim().toLowerCase();
  const recordedShown = needle
    ? recorded.filter((q) => q.toLowerCase().includes(needle))
    : recorded;
  const recentShown = recent.filter((q) => !recorded.includes(q));

  return (
    <section className="s-start" data-screen="start">
      <div className="st">
        <section className="st-l">
          <Cap>One question</Cap>
          <h1>What do you want to understand?</h1>
          <form className="ask-field" onSubmit={(e) => onSearch(e)}>
            <label className="sr-only" htmlFor="rrm-ask">A question, a title or a topic</label>
            <input id="rrm-ask" aria-label="Question" title={draft || undefined} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="A question, a title or a topic" autoFocus autoComplete="off" list="rrm-recorded" />
            <button className="b1-go press" type="submit" aria-label="Search" disabled={pending || !draft.trim()}>
              <Icon name="search" size={22} />
            </button>
          </form>
          {recorded.length > 0 && (
            <div className="b1-recorded">
              <p className="b1-recorded-k">{needle && recordedShown.length === 0 ? "No recorded question matches that." : "Recorded"}</p>
              {recordedShown.length > 0 && (
                <p className="b1-try">
                  {recordedShown.map((q) => (
                    <button key={q} type="button" className="press" data-recorded={q} onClick={() => onSearch({ preventDefault() {}, query: q })}>{q}</button>
                  ))}
                </p>
              )}
            </div>
          )}
          {recentShown.length > 0 && (
            <p className="b1-try">
              {recentShown.map((q) => (
                <button key={q} type="button" className="press" onClick={() => onSearch({ preventDefault() {}, query: q })}>{q}</button>
              ))}
            </p>
          )}
        </section>
        <div className="st-r">
          <BootPanel engine={engine} phase={phase} pending={pending} />
        </div>
      </div>
      <footer className="b1-foot"><span>Papers and citations: <a href="https://www.semanticscholar.org/">Semantic Scholar</a></span></footer>
    </section>
  );
}
