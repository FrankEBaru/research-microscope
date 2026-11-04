"use client";
import { useEffect, useRef, useState } from "react";
import { Rich } from "@/lib/math";
import { ask, explain, preparePhrases } from "@/lib/backend.js";
import { cleanExtract, markMidStart, storeLine } from "@/lib/extract.js";
import { draftKey, legacyKey, loadDraft, saveDraft } from "@/lib/draft.js";
import { storageFault } from "@/lib/faults.js";
import { Button, Cap, Icon, Prov } from "@/components/ui";
import { Pulse } from "@/components/ui/Pulse";
import Notice from "@/components/faults/Notice";
import "@/styles/box.css";

const PARTS = [
  ["coincide", "Matches"],
  ["contradice", "Contradicts"],
  ["sin_respaldo", "No support"],
  ["te_falto", "You missed"],
] as const;
// RRM-95: one glyph per verdict, so the strip reads without color too.
const GLYPH: Record<string, string> = { coincide: "≈", contradice: "≠", sin_respaldo: "∅", te_falto: "+" };

const NO_SUPPORT = "I didn't find this in the selected extracts from the paper.";
const EMPTY_PHRASES = "No saved sentences for these papers.";
const ASK_FAULT = "I couldn't review your explanation just now. The extracts stay below.";
const ASK_SLOW = "The quote check is still running. Review again if it does not appear.";

function sigOf(snap: { text: string; result: any; err: string; store: any }) {
  try { return JSON.stringify(snap); } catch { return String(snap.text || ""); }
}

function memory() {
  try { return typeof localStorage === "undefined" ? null : localStorage; } catch { return null; }
}

function tab() {
  try { return typeof sessionStorage === "undefined" ? null : sessionStorage; } catch { return null; }
}

function normSent(value: string) {
  return String(value || "")
    .replace(/^…/, "")
    .replace(/\$([^$]*)\$/g, (_, inner) => String(inner).replace(/[{}_\\]/g, ""))
    .replace(/[\u200b\u200c\u200d\ufeff]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Texto que se ve: sin MathML, que repite el LaTeX al lado del glifo. */
function visibleSent(node: Element) {
  let out = "";
  const walk = (cur: Node) => {
    if (cur.nodeType === 3) { out += cur.nodeValue || ""; return; }
    if (cur.nodeType !== 1) return;
    const el = cur as Element;
    if (el.matches("math, annotation, .katex-mathml")) return;
    for (const child of el.childNodes) walk(child);
  };
  walk(node);
  return normSent(out);
}

function sentEl(text: string) {
  if (typeof document === "undefined") return null;
  const want = normSent(text);
  if (!want) return null;
  const nodes = document.querySelectorAll(".sent");
  for (const node of nodes) {
    if (visibleSent(node) === want) return node as HTMLElement;
  }
  return null;
}

function group(rows: any[]) {
  const map = new Map<string, any[]>();
  for (const row of rows || []) {
    const key = String(row.paper);
    const list = map.get(key) || [];
    if (!list.some((item) => item.text === row.text)) list.push(row);
    map.set(key, list);
  }
  return [...map.entries()];
}

function absenceNote(note: string) {
  const text = String(note || "");
  if (/no hay clave/i.test(text)) return "No feedback: there is no key.";
  if (/apagado/i.test(text)) return "No feedback: Meta is off.";
  if (/no hubo red/i.test(text)) return "No feedback: there was no network.";
  if (/Sin retroalimentación/i.test(text)) return "No feedback for this review.";
  return "";
}

function storeCopy(store: any, done: boolean) {
  const line = storeLine(store, done);
  if (!line) return "";
  const ready = Number(store?.ready || 0);
  const total = Number(store?.total || 0);
  if (ready >= total) return `Sentences ready from all ${total} papers.`;
  const rest = total - ready;
  if (done) {
    const other = rest === 1 ? "The other has" : `The other ${rest} have`;
    return `Sentences ready from ${ready} of ${total} papers. ${other} no text available right now.`;
  }
  return `Preparing sentences: ${ready} of ${total} papers…`;
}

export default function AskBox({ sectionLabel, ids, focusId, onOpen, closed, onSkip, onPromote, onName, sectionId, variant = "slot" }: {
  sectionLabel: string;
  ids?: string[];
  focusId?: string;
  onOpen?: (id: string, why: string) => void;
  closed?: boolean;
  onSkip?: () => void;
  onPromote?: () => void;
  onName?: (id: string, section?: string) => string;
  sectionId?: string;
  variant?: "section" | "slot";
}) {
  const [text, setText] = useState("");
  const [only, setOnly] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [store, setStore] = useState<any>(null);
  const [err, setErr] = useState("");
  const [progress, setProgress] = useState("");
  const [phraseLine, setPhraseLine] = useState("");
  const [slow, setSlow] = useState(false);
  const [shown, setShown] = useState(0);
  const [storeDone, setStoreDone] = useState(false);
  const [savedOn, setSavedOn] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [jumps, setJumps] = useState<string[]>([]);
  const phrases = useRef<Promise<unknown> | null>(null);
  const answer = useRef<HTMLDivElement | null>(null);
  const baseline = useRef("");
  const key = (ids || []).join(",");

  useEffect(() => {
    const box = memory();
    const session = tab();
    let snap = box && focusId ? loadDraft(box, draftKey(focusId, sectionId)) : null;
    // La clave vieja vivía en sessionStorage. localStorage nunca la tuvo.
    if (!snap && box && focusId) {
      const oldKey = legacyKey(focusId);
      const old = loadDraft(session, oldKey);
      if (old) {
        snap = {
          text: old.text || "",
          result: old.result ?? null,
          err: old.err || "",
          store: old.store ?? null,
          at: typeof old.at === "number" ? old.at : Date.now(),
        };
        if (saveDraft(box, draftKey(focusId, sectionId), snap)) {
          try { session?.removeItem(oldKey); } catch { /* la copia nueva ya quedó */ }
        }
      }
    }
    const next = {
      text: snap?.text || "",
      result: snap?.result ?? null,
      err: snap?.err || "",
      store: snap?.store ?? null,
    };
    baseline.current = sigOf(next);
    setText(next.text);
    setResult(next.result);
    setErr(next.err);
    setStore(next.store);
    setSavedOn(Boolean(next.text.trim()));
    setHydrated(true);
  }, [focusId, sectionId]);

  const snapSig = hydrated ? sigOf({ text, result, err, store }) : "";
  useEffect(() => {
    if (!hydrated || !focusId) return;
    if (snapSig === baseline.current) {
      if (text.trim()) setSavedOn(true);
      return;
    }
    setSavedOn(false);
    let show = 0;
    const wait = window.setTimeout(() => {
      const snap = { text, result, err, store, at: Date.now() };
      const ok = saveDraft(memory(), draftKey(focusId, sectionId), snap);
      if (!ok) { storageFault(new Error("draft"), "askbox"); return; }
      baseline.current = snapSig;
      show = window.setTimeout(() => setSavedOn(true), 1200);
    }, 400);
    return () => { window.clearTimeout(wait); window.clearTimeout(show); };
  }, [hydrated, focusId, sectionId, snapSig]);

  useEffect(() => {
    if (!focusId) { setPhraseLine(""); phrases.current = null; return; }
    let stop = false;
    const t0 = Date.now();
    setPhraseLine("Preparing sentences from this paper… 0 s");
    const clock = window.setInterval(() => {
      setPhraseLine(`Preparing sentences from this paper… ${Math.round((Date.now() - t0) / 1000)} s`);
    }, 400);
    const job = preparePhrases(focusId).then(
      () => { if (!stop) { window.clearInterval(clock); setPhraseLine(""); } },
      () => { if (!stop) { window.clearInterval(clock); setPhraseLine(""); } },
    );
    phrases.current = job;
    return () => { stop = true; window.clearInterval(clock); };
  }, [focusId]);

  const keepStore = (body: any) => {
    const next = body?.store;
    if (!next) return;
    setStore((prev: any) => {
      if (!prev || prev.total !== next.total) return next;
      return { ...next, ready: Math.max(prev.ready || 0, next.ready || 0) };
    });
  };

  useEffect(() => {
    if (!key) return;
    let stop = false;
    let timer = 0;
    let same = 0;
    let last = -1;
    let tries = 0;
    setStoreDone(false);
    // Se para tras 8 lecturas sin cambio (~16 s) o 30 intentos (~1 min).
    const tick = async () => {
      try {
        const body = await ask(ids || [], "", "", focusId);
        if (stop) return;
        keepStore(body);
        const ready = Number(body?.store?.ready || 0);
        same = ready === last ? same + 1 : 0;
        last = ready;
        tries += 1;
        if (body?.store && ready < body.store.total && same < 8 && tries < 30) timer = window.setTimeout(tick, 2000);
        else setStoreDone(true);
      } catch { /* el envío dice si no hubo almacén */ }
    };
    tick();
    return () => { stop = true; window.clearTimeout(timer); };
  }, [key]);

  const send = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setErr("");
    setSlow(false);
    onPromote?.();
    try {
      if (phrases.current) await phrases.current;
      setPhraseLine("");
      setProgress("Looking for sentences in the papers…");
      let ranked: any = null;
      for (let attempt = 0; attempt < 60; attempt++) {
        ranked = await ask(ids || [], text, "frases", focusId);
        setResult(ranked);
        keepStore(ranked);
        if (!/Preparando los vectores/.test(ranked?.note || "")) break;
        setProgress("Preparing sentences from this paper…");
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
      }
      if (ranked?.empty) return;
      setProgress("Checking each quote…");
      const body = await ask(ids || [], text, "revisar", focusId);
      if (body?.empty) setResult(body);
      else { setResult(body); keepStore(body); setShown((n) => n + 1); }
    } catch (caught: any) {
      const timed = caught?.kind === "timeout" || caught?.name === "AbortError" || caught?.code === "F-ASK-SLOW";
      if (timed) setSlow(true);
      else setErr(explain(caught) || "F-ASK");
    } finally {
      setBusy(false);
      setProgress("");
    }
  };

  useEffect(() => {
    if (!shown) return;
    const frame = requestAnimationFrame(() => {
      answer.current?.scrollIntoView({ block: "start" });
    });
    return () => cancelAnimationFrame(frame);
  }, [shown]);

  const groups = group(result?.extracts || []);
  useEffect(() => {
    const scan = () => {
      const next: string[] = [];
      for (const [id, rows] of group(result?.extracts || [])) {
        if (String(id) !== String(focusId || "")) continue;
        rows.forEach((row, index) => {
          const shownText = markMidStart(cleanExtract(row.text));
          if (sentEl(shownText)) next.push(`${id}:${index}`);
        });
      }
      setJumps((prev) => (prev.join("|") === next.join("|") ? prev : next));
    };
    let timer = 0;
    let stop = false;
    const run = () => { if (!stop) scan(); };
    run();
    const root = document.querySelector(".paper");
    if (!root) return () => { stop = true; };
    const obs = new MutationObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(run, 250);
    });
    obs.observe(root, { childList: true, subtree: true });
    return () => { stop = true; obs.disconnect(); window.clearTimeout(timer); };
  }, [result, focusId]);

  const jumpTo = (shownText: string) => {
    const el = sentEl(shownText);
    if (!el) return;
    el.scrollIntoView({ block: "center" });
    el.classList.remove("flash");
    void el.offsetWidth;
    el.classList.add("flash");
  };

  const parts = result?.parts || {};
  const hasParts = PARTS.some(([id]) => (parts[id] || []).length);
  const listed = (result?.extracts || []).length;
  const citeOf = (id: string, section?: string) => onName?.(String(id), section) || "paper";
  const openPaper = String(focusId || "");
  const linked = (id: string) => String(id || "") === openPaper;
  const missing = absenceNote(result?.note || "");
  const storeText = store && store.total > 0 ? storeCopy(store, storeDone) : "";
  const live = phraseLine || progress;

  return (
    <form className="ask-card box" data-variant={variant} aria-label="Your words" onSubmit={send}>
      {closed && variant !== "section" && (
        <p className="box-offer">You closed a section. You can write or keep going.{" "}
          <button type="button" className="link" onClick={onSkip}>Continue</button>
        </p>
      )}
      <header className="box-h">
        <Icon name="pen" />
        <h3>Your words · <Rich text={sectionLabel} /></h3>
        {savedOn && <span className="saved"><Icon name="check" size={14} />Draft saved</span>}
      </header>
      {storeText && <Notice kind="absence">{storeText}</Notice>}
      <textarea className="you" aria-label="Your words" value={text} onChange={(event) => setText(event.target.value)} placeholder="In your words. Put LaTeX between $." />
      {text.includes("$") && <div className="ask-preview box-preview" aria-hidden="true"><Rich text={text} /></div>}
      <div className="box-act">
        <Button variant="primary" type="submit" disabled={busy || !text.trim()}>Review</Button>
      </div>
      {(busy || live) && !err && <Pulse mode="ai" compact detail="Answering…" />}
      {live && <p className="box-status tnum" aria-live="polite">{live}</p>}
      {(err || slow) && <Pulse mode="error" compact detail={err ? ASK_FAULT : ASK_SLOW} />}
      {slow && <Notice kind="fault" code="F-ASK-SLOW">{ASK_SLOW}</Notice>}
      {err && <Notice kind="fault" code="F-ASK">{ASK_FAULT}</Notice>}
      {result?.empty && <Notice kind="absence">{result.note || EMPTY_PHRASES}</Notice>}
      {missing && <Notice kind="absence">{missing}</Notice>}
      <div className="ask-result feedback" ref={answer}>
        {hasParts && (
          <div className="verdicts" role="group" aria-label="Review">
            {PARTS.map(([id, label]) => {
              const n = (parts[id] || []).length;
              if (!n) return null;
              const on = only === id;
              return (
                <button key={id} type="button" className={`vd press${on ? " is-on" : ""}`} data-v={id} aria-pressed={on} onClick={() => setOnly(on ? "" : id)}>
                  <b aria-hidden="true">{GLYPH[id]}</b>{label}<span className="tnum">{n}</span>
                </button>
              );
            })}
            <span className="box-prov"><Prov kind="simulado" text="Generated review" /></span>
          </div>
        )}
        {!result?.empty && PARTS.map(([id, label]) => (parts[id] || []).length && (!only || only === id) ? (
          <section key={id} className="vd-sec" data-v={id}>
            {(parts[id] || []).map((item: any, index: number) => (
              <div className="claim" key={index}>
                <p className="claim-h"><span className="vd-tag" data-v={id}><b aria-hidden="true">{GLYPH[id]}</b>{label}</span></p>
                <p className="claim-you"><Rich text={item.text} /></p>
                {item.cite && (
                  <blockquote className={linked(item.paper_id) ? "ex is-linked" : "ex"}>
                    <p><Rich text={markMidStart(item.cite)} /></p>
                    <footer>
                      {item.verified && <Prov kind="calculo" text="quotes checked" />}
                      {item.paper_id && (
                        <button type="button" className="box-jump" onClick={() => onOpen?.(String(item.paper_id), "cita en la caja")}>{citeOf(String(item.paper_id), item.section)}</button>
                      )}
                    </footer>
                  </blockquote>
                )}
                {id === "sin_respaldo" && <p className="claim-miss">{NO_SUPPORT}</p>}
              </div>
            ))}
          </section>
        ) : null)}
        {result && !result.empty && (
          <>
            <Cap gap>{result.papers === 1 ? "The paper says" : `These papers say (${result.papers})`}{result.matched > listed ? <span className="cap-n tnum"> · {listed} of {result.matched} nearby</span> : null}</Cap>
            {groups.map(([id, rows]) => rows.map((row: any, index: number) => {
              const shownText = markMidStart(cleanExtract(row.text));
              const canJump = jumps.includes(`${id}:${index}`);
              return (
                <blockquote key={`${id}-${index}`} className={linked(id) ? "ex is-linked" : "ex"}>
                  <p><Rich text={shownText} /></p>
                  <footer>
                    <Prov kind="paper" text={row.section || "paper"} />
                    {!linked(id) && (
                      <button type="button" className="box-jump" onClick={() => onOpen?.(id, "cita en la caja")}>{citeOf(id, row.section)}</button>
                    )}
                    {canJump && (
                      <button type="button" className="box-jump" onClick={() => jumpTo(shownText)}>Go to sentence →</button>
                    )}
                  </footer>
                </blockquote>
              );
            }))}
          </>
        )}
        {result?.note && !missing && !result.empty && <p className="box-note">{result.note}</p>}
      </div>
    </form>
  );
}
