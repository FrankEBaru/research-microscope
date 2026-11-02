"use client";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Block, Inline, Paper } from "@/lib/types";
import { Tex, Rich, Sym } from "@/lib/math";
import { ProvChip } from "./Bits";
import Instrument from "./Instrument";
import { bibtex } from "@/lib/bibtex.js";
import { eqTex, fetchNotes, paperKey, refText, sourcePdfUrl } from "@/lib/backend.js";
import { collectV2 } from "@/lib/artifacts.js";
import { pdfPagesOnly, polishText, presentInlines, visibleInlines } from "@/lib/prose.js";
import { faltaText } from "@/lib/falta.js";
import { hasConclusion, scanIds } from "@/lib/scan.js";
import { citeName } from "@/lib/layout.js";
import { UNDEFINED, symbolHover } from "@/lib/hover.js";
import AskBox from "./AskBox";
import "@/styles/lectura.css";

// Pop de oración con la maqueta «ejemplo simulado… no está conectado». Apagado en core; NEXT_PUBLIC_RRM_SENTENCE_MOCK=1 lo vuelve a mostrar.
const SENTENCE_MOCK = process.env.NEXT_PUBLIC_RRM_SENTENCE_MOCK === "1";
import ReadMinimap from "./ReadMinimap";
import { createTracker } from "@/lib/companion.js";
import { analyze } from "@/lib/tablechart.js";
import Companion, { Offer } from "./Companion";
import { Ctx, plainOf } from "./paper/inline";
import { GapView, ShapePill, artsAt, notesAt, repeatsBlock } from "./paper/GapNotes";
import Popover, { PopState } from "./paper/Popover";
import { Table } from "./paper/TableFig";
import { CropStrip, FigImg, ZoneFig } from "./paper/Figures";
import Margin, { MarginNote } from "./paper/Margin";
import { Boundary, Notice } from "./faults";
import { Cap, Icon, Prov, Segmented } from "./ui";
import type { AtlasCtx } from "./screens/types";

export { plainOf } from "./paper/inline";
export { GapView } from "./paper/GapNotes";

/** Número de nota estable. No muta un contador compartido: en dev React corre el render dos veces. */
function stampNotes(inls: Inline[], start: number): { inls: Inline[]; last: number } {
  let n = start;
  const walk = (list: Inline[]): Inline[] => (list || []).map((x) => {
    if (!x || typeof x !== "object") return x;
    if (x.t === "note") return { ...x, n: ++n };
    if (Array.isArray(x.c)) return { ...x, c: walk(x.c) };
    return x;
  });
  return { inls: walk(inls), last: n };
}

const noteCache = new Map<string, any>();

export function Inlines({ inls, ctx }: { inls: Inline[]; ctx: Ctx }) {
  const shown = presentInlines(inls);
  return <>{shown.map((x, i) => <One key={i} x={x} ctx={ctx} prev={i ? plainOf([shown[i - 1]]) : ""} />)}</>;
}

function One({ x, ctx, prev = "" }: { x: Inline; ctx: Ctx; prev?: string }) {
  switch (x.t) {
    case "text": return <>{x.v.replaceAll("~", "\u00a0")}</>;
    case "math": {
      if (!ctx.core) return <Tex tex={x.v} display={false} syms={ctx.syms} />;
      const token = encodeURIComponent(x.v).replace(/\|/g, "%7C");
      const marked = ctx.pin?.kind === "tex" && x.v.replace(/\s+/g, "") === ctx.pin.val;
      return (
        <span data-pop={`m|${ctx.block}|${ctx.sent}|${token}`} data-tex={x.v} data-pin={marked ? "1" : undefined} className={marked ? "sym-mark" : undefined}>
          <Tex tex={x.v} display={false} syms={ctx.syms} />
        </span>
      );
    }
    case "em": return <em><Inlines inls={x.c} ctx={ctx} /></em>;
    case "strong": return <strong><Inlines inls={x.c} ctx={ctx} /></strong>;
    case "span": return <Inlines inls={x.c} ctx={ctx} />;
    case "code": return <code>{x.v}</code>;
    case "link": {
      if (x.href.startsWith("#")) {
        const lab = x.href.slice(1), shown = ctx.xref?.[lab];
        const raw = plainOf(x.c);
        return <a href={x.href} className="xref" data-xref={lab} {...(ctx.figs?.has(lab) ? { "data-pop": `f|${lab}`, tabIndex: 0 } : {})}>{shown && (raw === `[${lab}]` || raw === lab) ? shown : <Inlines inls={x.c} ctx={ctx} />}</a>;
      }
      return <a href={x.href} target="_blank" rel="noreferrer"><Inlines inls={x.c} ctx={ctx} /></a>;
    }
    case "cite": {
      const lab = x.keys.map((k: string) => ctx.refLabels?.[k] ?? ctx.refIndex[k] ?? k);
      const key = `c|${x.keys.join(",")}`;
      const open = ctx.popKey === key;
      return (
        <span className="cite-wrap">
          <button type="button" className={`cite${open ? " is-open" : ""}`} aria-expanded={open} data-pop={key}>{lab.join("; ")}</button>
        </span>
      );
    }
    case "note": {
      const n = x.n || 0;
      return <sup className="fn" id={n ? `fn-${n}` : undefined} tabIndex={0} data-pop={`n|${n}`}>{n}</sup>;
    }
    case "ref": {
      const label = x.label || "";
      let text = refText(x, ctx.xref);
      if (/(?:figure|fig\.|table|tab\.|section|sec\.|equation|eq\.|appendix|figura|tabla|sección|ecuación|apéndice)\s*~?\s*$/i.test(prev) && /^(Figure|Table|Section|Appendix|equation|Figura|Tabla|Sección|Apéndice|ecuación)\s+/.test(text)) {
        text = text.replace(/^\S+\s+/, "");
      }
      const href = x.target ? `#blk-${x.target}` : `#${label}`;
      return <a href={href} className="xref" data-xref={label}>{text}</a>;
    }
    default: return null;
  }
}

function autoSentence(text: string) {
  const parts = String(text || "").split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
  return parts.find((s) => /we propose|we present|we show|we introduce/i.test(s)) || parts[0] || "";
}

const NAME_STOP = new Set(["equal", "contribution", "listing", "order", "random", "work", "performed", "while", "with", "and", "the", "for", "from"]);

function authorPeople(raw: string[]) {
  const out: string[] = [];
  for (const item of raw || []) {
    let head = String(item || "").replace(/\s+/g, " ").trim();
    if (!head || head.includes("@")) continue;
    head = head.split(/\d/)[0].replace(/[.,;:]+$/, "").trim();
    const words = head.split(" ").map((w) => w.replace(/,$/, "")).filter(Boolean);
    const name: string[] = [];
    for (const w of words) {
      const bare = w.replace(/\./g, "");
      if (!bare || NAME_STOP.has(bare.toLowerCase())) break;
      if (!/^[\p{L}][\p{L}'’.-]*$/u.test(bare)) break;
      const titled = bare[0] === bare[0].toUpperCase();
      if (!titled && !(name.length === 0 && words.length <= 3)) break;
      name.push(w);
      if (name.length === 3) break;
    }
    const line = name.join(" ");
    if (name.length >= 2 && !out.includes(line)) out.push(line);
  }
  return out;
}

function authorLine(raw: string[]) {
  const people = authorPeople(raw);
  const use = people.length ? people : (raw || []).map((s) => String(s || "").trim()).filter((s) => s && !s.includes("@")).slice(0, 3);
  if (use.length > 4) return `${use.slice(0, 3).join(", ")} and ${use.length - 3} more`;
  return use.join(", ");
}

function paperLang(paper: Paper) {
  const raw = String((paper as any).lang || (paper as any).language || "").toLowerCase();
  return /^[a-z]{2}/.test(raw) ? raw.slice(0, 2) : "en";
}

function peekReadFlag(core: boolean, id: unknown) {
  if (!core || id == null || typeof sessionStorage === "undefined") return false;
  try { return sessionStorage.getItem(`rrm.read.${id}`) === "1"; }
  catch { return false; }
}

function pinOf(key: string) {
  const cut = key.indexOf(":");
  if (cut < 0) return null;
  return { kind: key.slice(0, cut), val: key.slice(cut + 1) };
}

function pinTex(pin: { kind: string; val: string }, att: any) {
  if (pin.kind === "tex") return pin.val;
  const hit = (att?.symbols || []).find((s: any) => s.id === pin.val);
  return hit?.latex || pin.val;
}

function pinName(pin: { kind: string; val: string }, att: any) {
  const syms = att?.symbols || [];
  if (pin.kind === "id") return syms.find((s: any) => s.id === pin.val)?.name || "";
  return syms.find((s: any) => String(s.latex || "").replace(/\s+/g, "") === pin.val)?.name || "";
}

function SymbolMargin({ tex, name, blocks, at }: { tex: string; name: string; blocks: Block[]; at?: { block: string; index: number } | null }) {
  const hit = symbolHover(blocks, tex, at || undefined);
  const missing = !hit || hit.text === UNDEFINED;
  return (
    <>
      <p className="sn-sym">
        <span className="sn-s"><Tex tex={tex} /></span>
        {name && <span className="sn-d">{name}</span>}
      </p>
      {missing
        ? <Notice kind="absence">the paper does not define it</Notice>
        : <>
            <p className="sn-q">“{hit.text}”</p>
            <p><Prov kind="paper" text={hit.section || "paper"} /></p>
          </>}
    </>
  );
}

export function mountKey(paper: Paper) {
  if (!paper.stage || paper.stage === "stub") return "stub";
  return paper.upgraded_from ? "body-up" : "body";
}

export default function PaperView({ paper, content, focus, companion, onHideCompanion, remote, showInstrument = true, showCrops = true, core = false, burstIds, map, explore, openId, onOpenPaper, onPromote, atlasCtx }: { paper: Paper; content: any; focus?: string; companion?: boolean; onHideCompanion?: () => void; remote?: { status?: string; stage?: string; reason?: string; source?: string; pdf?: boolean; oa_pdf?: string; arxiv?: string } | null; showInstrument?: boolean; showCrops?: boolean; core?: boolean; burstIds?: string[]; map?: { papers: any[]; edges: any[]; layout: any } | null; explore?: { nodes?: any[]; edges?: any[] } | null; openId?: string; onOpenPaper?: (id: string, why: string) => void; onPromote?: () => void; atlasCtx?: AtlasCtx }) {
  const art = useRef<HTMLElement>(null);
  const [pop, setPop] = useState<PopState>(null);
  const [pack, setPack] = useState<any>(null);
  const [symHot, setSymHot] = useState("");
  const [symPin, setSymPin] = useState("");
  const [pinAt, setPinAt] = useState<{ block: string; index: number } | null>(null);
  const [reading, setReading] = useState(false);
  const [openAsk, setOpenAsk] = useState("");
  const [copied, setCopied] = useState("");
  const [wide, setWide] = useState(true);
  const [prog, setProg] = useState(0);
  const timer = useRef<any>(null);
  const [active, setActive] = useState<string>("");
  const tracker = useRef(createTracker());
  const [offer, setOffer] = useState<Offer | null>(null);
  const [point, setPoint] = useState<string | null>(null);
  useEffect(() => { if (!point) return; const el = document.getElementById(point); el?.classList.remove("flash"); void el?.offsetWidth; el?.classList.add("flash"); const t = setTimeout(() => setPoint(null), 12000); return () => clearTimeout(t); }, [point]);
  useEffect(() => { if (companion && focus) setPoint(`blk-${focus}`); }, [focus, companion, paper.arxivId]);
  const [breakdown, setBreakdown] = useState<string | null>(null);
  useEffect(() => { tracker.current.reset(); setOffer(null); }, [paper.arxivId, paper.stage, paper.upgraded_from, companion]);

  const paperId = paper.corpusid != null ? String(paper.corpusid) : (paper.arxivId || "");
  useEffect(() => {
    const on = peekReadFlag(core, paper.corpusid);
    setReading(on);
    let timer = 0;
    if (on && paper.corpusid != null) {
      const key = `rrm.read.${paper.corpusid}`;
      timer = window.setTimeout(() => { try { sessionStorage.removeItem(key); } catch { /* storage blocked */ } }, 0);
    }
    setOpenAsk("");
    setSymPin("");
    setPinAt(null);
    setPop(null);
    setCopied("");
    return () => window.clearTimeout(timer);
  }, [paperId, core]);

  useLayoutEffect(() => {
    const mq = window.matchMedia("(min-width: 1200px)");
    const apply = () => setWide(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  const local = useMemo(() => collectV2(paper.blocks || []), [paper]);
  const att = content.attention?.paper === paper.arxivId ? content.attention : null;
  const model = useMemo(() => {
    const syms: Sym[] = att ? att.symbols : [];
    const refIndex: Record<string, number> = {};
    Object.keys(paper.refs || {}).forEach((k, i) => (refIndex[k] = i + 1));
    const byLabel: Record<string, any> = {}, figs = new Set<string>();
    const byId: Record<string, any> = {}, secOf: Record<string, string> = {}, nums: Record<string, string> = {};
    const notes: { blocks: Block[] }[] = [];
    const noteBase: Record<string, number> = {};
    const toc: { id: string; label: string; num: string; level: number }[] = [];
    let h = [0, 0, 0], cur = "", fig = 0, tab = 0, app = false;
    const xref: Record<string, string> = {}, target: Record<string, string> = {};
    const letter = (n: number) => String.fromCharCode(64 + n);
    const figN: Record<string, number> = {}, tabN: Record<string, number> = {};
    const walk = (inls: Inline[]) => (inls || []).forEach((x) => { if (x.t === "note") notes.push({ blocks: x.blocks }); else if (Array.isArray(x.c)) walk(x.c); });
    for (const b of paper.blocks) {
      byId[b.id] = b; noteBase[b.id] = notes.length;
      if (b.kind === "h" && b.unnumbered) {
        cur = ""; toc.push({ id: b.id, label: polishText(plainOf(b.inlines)), num: "", level: 1 });
        if (/^(appendix|ap[ée]ndice)/i.test(plainOf(b.inlines))) { app = true; h = [0, 0, 0]; }
      } else if (b.kind === "h" && b.level <= 3) {
        if (b.number != null) cur = String(b.number);
        else {
          h[b.level - 1]++; for (let j = b.level; j < 3; j++) h[j] = 0;
          cur = h.slice(0, b.level).map((n, i) => (app && i === 0 ? letter(n) : n)).join(".");
        }
        nums[b.id] = cur;
        if (b.label) { xref[b.label] = `${app ? "Appendix" : "Section"} ${cur}`; target[b.label] = `sec-${b.id}`; }
        if (b.level <= 2) toc.push({ id: b.id, label: polishText(plainOf(b.inlines)), num: cur, level: b.level });
      }
      secOf[b.id] = cur;
      if (b.kind === "fig") { figN[b.id] = ++fig; if (b.label) { xref[b.label] = `Figure ${fig}`; byLabel[b.label] = b; figs.add(b.label); } }
      if (b.kind === "eq") {
        const tg = /\\tag\{([^}]*)\}/.exec(b.tex);
        (b.labels || []).forEach((l: string) => {
          if (b.number != null) xref[l] = String(l).startsWith("eq") ? `(${b.number})` : String(b.number);
          else xref[l] = tg ? `(${tg[1]})` : "equation";
          target[l] = `blk-${b.id}`;
        });
      }
      if (b.kind === "table") {
        b.an = analyze(b as any);
        tabN[b.id] = ++tab; if (b.label) xref[b.label] = `Table ${tab}`;
      }
      walk(b.inlines);
    }
    return { syms, refIndex, byId, secOf, nums, notes, noteBase, toc, figN, tabN, xref, target, byLabel, figs };
  }, [paper, att]);

  const onOver = (e: React.MouseEvent | React.FocusEvent) => {
    const el = (e.target as HTMLElement).closest("[data-pop],[data-sym]") as HTMLElement | null;
    clearTimeout(timer.current);
    if (!el) return;
    const key = el.dataset.pop || `y|${el.dataset.sym}`;
    if (core) {
      const host = (e.target as HTMLElement).closest("[data-sym],[data-tex]") as HTMLElement | null;
      const sym = host?.dataset.sym ? `id:${host.dataset.sym}` : host?.dataset.tex ? `tex:${host.dataset.tex.replace(/\s+/g, "")}` : "";
      if (sym) setSymHot(sym);
    }
    if (core && !SENTENCE_MOCK && key.startsWith("s|")) {
      const parts = key.split("|");
      const has = (pack?.notes || []).some((n: any) => n.block_id === parts[1] && n.sent_index === +parts[2]);
      if (!has) return;
    }
    if (key.startsWith("e|") || key.startsWith("n|")) return;
    if (companion) signal(key);
    const show = () => setPop({ key, rect: el.getBoundingClientRect() });
    if (key.startsWith("s|")) timer.current = setTimeout(show, 380); else show();
  };
  const signal = (key: string) => {
    const [kind, a, b] = key.split("|");
    const sk = kind === "y" ? `sym:${a}` : kind === "f" ? `fig:${a}` : kind === "t" ? `row:${a}:${b}` : "";
    if (!sk) return;
    const hit = tracker.current.track(sk);
    if (!hit) return;
    if (kind === "y" && att) {
      const sy = att.symbols.find((q: any) => q.id === a);
      setOffer({ key: hit, text: `Llevas un rato con «${sy.name}». ¿Te llevo a donde el paper lo define?`, accept: "Sí, llévame", onAccept: () => goTo(sy.def.anchor.blockId) });
    } else if (kind === "f") {
      setOffer({ key: hit, text: `Has vuelto varias veces a la ${model.xref[a]}. ¿Te llevo a ella?`, accept: "Sí, llévame", onAccept: () => document.getElementById(a)?.scrollIntoView({ behavior: "smooth", block: "center" }) });
    } else if (kind === "t") {
      setOffer({ key: hit, text: "Estás recorriendo esta tabla. ¿Te llevo a su leyenda, que explica qué mide?", accept: "Sí, llévame", onAccept: () => document.querySelector(`[data-tab="${a}"] figcaption`)?.scrollIntoView({ behavior: "smooth", block: "center" }) });
    }
  };
  const touched = useRef(0);
  const onOut = (e: { relatedTarget: EventTarget | null }) => {
    const next = e.relatedTarget as HTMLElement | null;
    if (next && typeof next.closest === "function" && next.closest(".popover")) return;
    if (Date.now() - touched.current < 800) return;
    clearTimeout(timer.current);
    setPop(null);
    setSymHot("");
  };
  useEffect(() => {
    const away = (e: TouchEvent) => { const t = e.target as HTMLElement; if (!t.closest?.("[data-pop],[data-sym],.popover")) setPop(null); };
    document.addEventListener("touchstart", away, { passive: true }); return () => document.removeEventListener("touchstart", away);
  }, []);
  const onClick = (e: React.MouseEvent) => {
    const t = e.target as HTMLElement;
    if (Date.now() - touched.current < 800 && !t.closest("[data-sym],[data-xref]")) { const el = t.closest("[data-pop]") as HTMLElement | null; const popKey = el?.dataset.pop || ""; if (el && !popKey.startsWith("s|") && !popKey.startsWith("n|") && !popKey.startsWith("e|")) setPop({ key: popKey, rect: el.getBoundingClientRect() }); }
    const sym = t.closest("[data-sym],[data-tex]") as HTMLElement | null;
    if (core && sym) {
      const mark = sym.dataset.sym ? `id:${sym.dataset.sym}` : sym.dataset.tex ? `tex:${sym.dataset.tex.replace(/\s+/g, "")}` : "";
      if (mark) {
        const host = sym.closest("[data-pop]") as HTMLElement | null;
        const parts = host?.dataset.pop?.split("|") || [];
        const off = symPin === mark;
        setSymPin(off ? "" : mark);
        if (off) setPinAt(null);
        else if (parts[0] === "m") setPinAt({ block: parts[1], index: Number(parts[2]) });
        else if (parts[0] === "e") setPinAt({ block: parts[1], index: 0 });
        else setPinAt(null);
        return;
      }
    }
    if (!core && sym && att) { const s = att.symbols.find((y: any) => y.id === sym.dataset.sym); if (s) goTo(s.def.anchor.blockId); return; }
    const xr = t.closest("[data-xref]") as HTMLElement | null;
    if (xr) { e.preventDefault(); const el = document.getElementById(model.target[xr.dataset.xref!] || xr.dataset.xref!); el?.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
    const cite = t.closest("[data-pop]") as HTMLElement | null;
    if (core && cite?.dataset.pop?.startsWith("c|")) {
      setPop({ key: cite.dataset.pop, rect: cite.getBoundingClientRect() });
      return;
    }
    const cp = t.closest("[data-copy]") as HTMLElement | null;
    if (cp) {
      const id = cp.dataset.copied || "copy";
      navigator.clipboard?.writeText(cp.dataset.copy || "");
      setCopied(id);
      window.setTimeout(() => setCopied((cur) => (cur === id ? "" : cur)), 1200);
    }
  };
  const esc = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const symsInTex = (tex: string): Sym[] => (att ? att.symbols : []).filter((y: Sym) => new RegExp(`(^|[^A-Za-z\\\\^_])${esc(y.latex)}`).test(tex));
  useEffect(() => {
    if (!companion || !att) return;
    const DWELL = (window as any).__RRM_DWELL_MS || 15000;
    const vis = new Map<string, number>(); let current: string | null = null; let timer: any;
    const arm = () => {
      clearTimeout(timer); if (!current) return; const id = current;
      timer = setTimeout(() => {
        const b = model.byId[id.replace("blk-", "")]; if (!b || symsInTex(b.tex).length === 0) return;
        const hit = tracker.current.offer(`dwell:${id}`); if (!hit) return;
        setOffer({ key: hit, text: "Llevas un rato en esta ecuación. ¿Te desgloso sus símbolos con lo que dice el paper?", accept: "Sí, desglósala", onAccept: () => { setBreakdown(b.id); setPoint(`blk-${b.id}`); setTimeout(() => document.getElementById(`bd-${b.id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 80); } });
      }, DWELL);
    };
    const io = new IntersectionObserver((es) => {
      es.forEach((e) => vis.set(e.target.id, e.intersectionRatio));
      current = [...vis].filter(([, r]) => r >= 0.9).map(([k]) => k)[0] || null; arm();
    }, { threshold: [0, 0.5, 0.9, 1] });
    document.querySelectorAll<HTMLElement>(".eq.blk").forEach((e) => io.observe(e));
    window.addEventListener("scroll", arm, { passive: true });
    return () => { clearTimeout(timer); io.disconnect(); window.removeEventListener("scroll", arm); };
  }, [companion, paper.arxivId, att]);
  const goTo = (id: string) => {
    const el = document.getElementById("blk-" + id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
  };
  useEffect(() => { if (focus) setTimeout(() => goTo(focus), 250); }, [focus, paper.arxivId]);
  const blockCount = (paper.blocks || []).length;
  useEffect(() => {
    if (!core || paper.corpusid == null || !blockCount) return;
    const key = String(paper.corpusid);
    const hit = noteCache.get(key);
    if (hit) { setPack(hit); return; }
    let stop = false;
    const timer = window.setTimeout(() => { stop = true; }, 22000);
    fetchNotes(key).then((body) => {
      if (stop) return;
      noteCache.set(key, body);
      setPack(body);
    }).catch(() => {
      if (stop) return;
      const empty = { notes: [], artifacts: [], usage: { cost_usd: 0 } };
      noteCache.set(key, empty);
      setPack(empty);
    });
    return () => { stop = true; window.clearTimeout(timer); };
  }, [core, paper.corpusid, blockCount]);
  useEffect(() => {
    const root = art.current;
    if (!root) return;
    root.querySelectorAll(".sym-mark").forEach((el) => el.classList.remove("sym-mark"));
    const key = symPin || symHot;
    if (!key) return;
    const cut = key.indexOf(":");
    const kind = key.slice(0, cut);
    const val = key.slice(cut + 1);
    root.querySelectorAll(kind === "id" ? "[data-sym]" : "[data-tex]").forEach((el) => {
      const node = el as HTMLElement;
      const cur = kind === "id" ? node.dataset.sym : (node.dataset.tex || "").replace(/\s+/g, "");
      if (cur === val) node.classList.add("sym-mark");
    });
  }, [symPin, symHot, paper, reading]);
  const pendingSec = useRef("");
  const toSection = (id: string) => {
    const el = document.getElementById(`sec-${id}`);
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    if (core && !reading && paper.full) { pendingSec.current = id; setReading(true); }
  };
  useEffect(() => {
    const id = pendingSec.current;
    if (!reading || !id) return;
    pendingSec.current = "";
    requestAnimationFrame(() => document.getElementById(`sec-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [reading]);
  useEffect(() => {
    const hs = Array.from(document.querySelectorAll<HTMLElement>("[data-toc]"));
    const io = new IntersectionObserver((es) => { es.forEach((e) => e.isIntersecting && setActive(e.target.id)); }, { rootMargin: "-10% 0px -80% 0px" });
    hs.forEach((h) => io.observe(h));
    return () => io.disconnect();
  }, [paper, reading]);
  useEffect(() => {
    const el = art.current;
    if (!el) return;
    let frame = 0;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      const view = window.innerHeight || 1;
      const total = el.offsetHeight - view;
      const next = total <= 8 ? (rect.bottom <= view ? 1 : 0) : Math.min(1, Math.max(0, -rect.top / total));
      setProg((prev) => (Math.abs(prev - next) < 0.005 ? prev : next));
    };
    const onScroll = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
  }, [paperId, reading, wide]);

  const instAfter = att?.instrument.claim.anchor.blockId;
  const authors = authorLine(paper.authors || []);
  const scan = core && !reading ? scanIds(paper.blocks) : null;
  const firstHead = (paper.blocks || []).find((b) => b.kind === "h");
  const sectionNow = active.startsWith("sec-") ? (paper.blocks || []).find((b) => b.kind === "h" && b.id === active.slice(4)) : firstHead;
  const sectionLabel = sectionNow ? polishText(plainOf(sectionNow.inlines)) : "Start";
  const abstractId = (paper.blocks || []).find((b) => b.kind === "p" && b.abs)?.id || "";
  const nameOf = (id: string, section?: string) => citeName((map?.papers || []).find((item) => paperKey(item) === String(id)), section);
  const focusId = paper.corpusid != null ? String(paper.corpusid) : "";
  const undrawn = core && (remote?.status === "abstract_only" || remote?.status === "failed");
  const arxivId = paper.arxivId || remote?.arxiv || "";
  const oaPdf = remote?.oa_pdf || paper.oaPdf || "";
  const pdfHref = remote?.pdf && paper.corpusid != null
    ? sourcePdfUrl(paper.corpusid)
    : arxivId
      ? `https://arxiv.org/pdf/${arxivId}`
      : (typeof oaPdf === "string" && oaPdf.startsWith("http") ? oaPdf : "");
  const honest = arxivId
    ? `https://arxiv.org/abs/${arxivId}`
    : paper.corpusid != null
      ? `https://www.semanticscholar.org/paper/${paper.corpusid}`
      : "";
  const burst = (atlasCtx?.papers || map?.papers || []).find((item) => paperKey(item) === (paper.corpusid != null ? String(paper.corpusid) : paper.arxivId));
  const metaBits: { key: string; text: string; tnum?: boolean }[] = [];
  if (paper.arxivId) metaBits.push({ key: "ax", text: `arXiv ${paper.arxivId}` });
  const year = burst?.year != null && burst.year !== "" ? String(burst.year) : (paper.date || "").slice(0, 4);
  const venue = burst?.venue ? String(burst.venue) : "";
  const place = [venue, year].filter(Boolean).join(" ");
  if (place) metaBits.push({ key: "place", text: place });
  const cites = burst?.citationcount ?? burst?.citationCount;
  if (cites != null && cites !== "") {
    const n = Number(cites);
    const shown = Number.isFinite(n) ? n.toLocaleString("en-US") : String(cites);
    metaBits.push({ key: "cites", text: `${shown} ${n === 1 ? "citation" : "citations"}`, tnum: true });
  }
  const quote = undrawn ? polishText(paper.abstract || "") : (remote ? polishText(autoSentence(paper.abstract)) : "");
  const pin = symPin ? pinOf(symPin) : null;
  const showMini = Boolean(core && (map || (explore?.nodes || []).length > 0));
  const showNav = model.toc.length > 0 || showMini;
  const pct = Math.round(prog * 100);

  const askBox = (variant: "slot" | "section", sectionId: string, label: string) => (
    <Boundary name="askbox">
      <div className={variant === "slot" ? "ask-slot" : undefined}>
        <AskBox variant={variant} sectionId={sectionId || undefined} sectionLabel={label} ids={burstIds} focusId={focusId} onOpen={onOpenPaper} onPromote={onPromote} onName={nameOf} />
      </div>
    </Boundary>
  );

  const side: MarginNote[] = [];
  const rows: ReactNode[] = [];
  if (!undrawn) {
    const stack: { id: string; level: number; title: string }[] = [];
    const closeUntil = (level: number) => {
      while (stack.length && stack[stack.length - 1].level >= level) {
        const sec = stack.pop()!;
        rows.push(
          <div key={`end-${sec.id}`} className="sec-end">
            {openAsk === sec.id
              ? askBox("section", sec.id, sec.title)
              : <button type="button" className="yw press" onClick={() => setOpenAsk(sec.id)}><Icon name="pen" /><span>Explain “{sec.title}” in your words</span></button>}
          </div>,
        );
      }
    };
    paper.blocks.forEach((b, bi) => {
      if (scan && !scan.has(b.id)) return;
      if (core && reading && b.kind === "h" && b.level <= 2) {
        closeUntil(b.level);
        stack.push({ id: b.id, level: b.level, title: polishText(plainOf(b.inlines)) });
      }
      const ctx: Ctx = { syms: model.syms, refIndex: model.refIndex, refLabels: paper.refLabels, xref: model.xref, figs: model.figs, counter: { n: model.noteBase[b.id] }, core, block: b.id, popKey: pop?.key, pin };
      let el: ReactNode = null;
      if (b.kind === "h") {
        const Tag: any = b.level === 1 ? "h2" : b.level === 2 ? "h3" : "h4";
        const num = model.nums[b.id];
        el = <Tag id={`sec-${b.id}`} data-toc>{num && <span className="no">{num}</span>}<Inlines inls={b.inlines} ctx={ctx} /></Tag>;
      } else if (b.kind === "p") {
        if (!b.abs && !visibleInlines(b.inlines)) return;
        let noteCursor = model.noteBase[b.id];
        const stampedSents = (b.sents || [b.inlines]).map((s: Inline[]) => {
          const hit = stampNotes(s, noteCursor);
          noteCursor = hit.last;
          return hit.inls;
        });
        const fnNums: number[] = [];
        const takeNums = (list: Inline[]) => (list || []).forEach((x) => {
          if (x?.t === "note" && x.n) fnNums.push(x.n);
          else if (Array.isArray(x?.c)) takeNums(x.c);
        });
        stampedSents.forEach(takeNums);
        const noted = (i: number) => (pack?.notes || []).some((n: any) => n.block_id === b.id && n.sent_index === i) || (SENTENCE_MOCK && core);
        const prose = (
          <div id={`blk-${b.id}`} className={`blk ${b.abs ? "abstract" : ""} ${b.raw ? "raw" : ""}`}>
            {b.abs && <div className="abs-label">Abstract</div>}
            <p>{stampedSents.map((s: Inline[], i: number) => {
              const key = `s|${b.id}|${i}`;
              return <span key={i} className={`sent${noted(i) ? " as" : ""}${pop?.key === key ? " is-hover" : ""}`} data-pop={key}>{i > 0 ? " " : null}<Inlines inls={s} ctx={{ ...ctx, sent: i }} /></span>;
            })}</p>
            {b.abs && remote && paper.tldr && <p className="tldr"><Prov kind="simulado" text="AI note" /> {paper.tldr}</p>}
            {fnNums.length > 0 && !wide && <ol className="notes">{fnNums.map((num) => { const n = model.notes[num - 1]; return n ? <li key={num} value={num}><Inlines inls={(n.blocks || []).flatMap((x: Block) => x.inlines || [])} ctx={{ ...ctx, counter: { n: 999 } }} /></li> : null; })}</ol>}
          </div>
        );
        if (wide && fnNums.length > 0) {
          fnNums.forEach((n) => {
            const note = model.notes[n - 1];
            if (!note) return;
            side.push({
              id: `fn-${n}`,
              anchor: `#fn-${n}`,
              dy: -6,
              body: (
                <>
                  <p className="sn-k"><sup>{n}</sup> Note</p>
                  <p><Inlines inls={(note.blocks || []).flatMap((x: Block) => x.inlines || [])} ctx={{ syms: model.syms, refIndex: model.refIndex, counter: { n: 999 }, core }} /></p>
                </>
              ),
            });
          });
        }
        const stepped = core && b.raw && artsAt(b.id, pack, local).some((a) => a.type === "pasos");
        el = stepped ? <details className="raw-tex"><summary>Show LaTeX</summary>{prose}</details> : prose;
      } else if (b.kind === "eq") {
        el = (
          <div id={`blk-${b.id}`} className={`eq blk${pop?.key === `e|${b.id}` ? " is-hover" : ""}`} {...(core ? { "data-pop": `e|${b.id}`, tabIndex: 0 } : {})}>
            <Tex tex={eqTex(b)} display syms={model.syms} />
            <button className="copy press" type="button" data-copy={b.tex} data-copied={b.id} aria-label={copied === b.id ? "Copied" : "Copy LaTeX"}>
              <Icon name="copy" size={14} />
              {copied === b.id ? "Copied" : "LaTeX"}
            </button>
          </div>
        );
      } else if (b.kind === "list") {
        el = <ul id={`blk-${b.id}`} className="blk list">{b.items.map((it: Inline[], i: number) => <li key={i}><Inlines inls={it} ctx={ctx} /></li>)}</ul>;
      } else if (b.kind === "fig") {
        const imgs = b.images || [];
        el = (
          <figure id={b.label || `blk-${b.id}`} className="fig blk">
            {imgs.length > 0 && <div className="fig-imgs">{imgs.map((src: string, i: number) => { const zs = i === 0 && b.label ? (content.zones?.figures || []).find((f: any) => f.paper === paper.arxivId && f.fig === b.label)?.zones : null;
              return zs ? <ZoneFig key={`${i}-${src}`} paper={paper} name={src} alt={plainOf(b.caption)} zones={zs} onGo={goTo} /> : <FigImg key={`${i}-${src}`} paper={paper} name={src} alt={plainOf(b.caption)} eager={i === 0} />; })}</div>}
            <figcaption><b>Figure {model.figN[b.id]}.</b> <Inlines inls={b.caption} ctx={ctx} /> <Prov kind="paper" text="original figure" /></figcaption>
          </figure>
        );
      } else if (b.kind === "table") {
        el = <Boundary name="table"><Table b={b} ctx={ctx} n={model.tabN[b.id]} predict={showInstrument} still={reading} /></Boundary>;
      }
      const gaps = gapPieces(b);
      const symbolHere = !wide && pin && pinAt?.block === b.id;
      const row = (
        <Boundary key={`${b.id}-${bi}`} name="row">
          <div className="row" data-blk={b.id}>
            {el}
            {breakdown === b.id && b.kind === "eq" && (
              <aside id={`bd-${b.id}`} className="breakdown" aria-label="Equation breakdown">
                <div className="chips"><Prov kind="curado" text="curated breakdown: symbols and definitions from the paper, not generated text" /></div>
                <ul>{symsInTex(b.tex).map((y: Sym) => (
                  <li key={y.id}><span className="sym-pill" style={{ color: y.color }}><Tex tex={y.latex} /></span> <b>{y.name}</b> · <em>«<Rich text={att.symbols.find((q: any) => q.id === y.id).def.quote} />»</em> <button className="link" onClick={() => goTo(att.symbols.find((q: any) => q.id === y.id).def.anchor.blockId)}>see where it is defined</button></li>
                ))}</ul>
                {showInstrument && /sqrt\{d_k\}/.test(b.tex) && <p className="small">This equation divides by √d_k: <button className="link" onClick={() => document.querySelector(".instrument")?.scrollIntoView({ behavior: "smooth", block: "start" })}>open it in the instrument</button> and check it.</p>}
                <button className="link" onClick={() => setBreakdown(null)}>close</button>
              </aside>
            )}
            {showInstrument && !undrawn && att && b.id === instAfter && <Instrument content={att} goTo={goTo} />}
            {symbolHere && (
              <div className="margin-inline sn sn--sym">
                <SymbolMargin tex={pinTex(pin!, att)} name={pinName(pin!, att)} blocks={paper.blocks} at={pinAt} />
              </div>
            )}
            {!wide && gaps}
          </div>
        </Boundary>
      );
      rows.push(row);
      if (core && !reading && b.id === abstractId) rows.push(<div key="ask-slot">{askBox("slot", abstractId, sectionLabel)}</div>);
    });
    if (core && reading) closeUntil(0);
    if (wide && pin && (!pinAt || !scan || scan.has(pinAt.block))) {
      side.push({
        id: `sym-${symPin}`,
        anchor: pin.kind === "tex" ? "[data-pin='1']" : ".sym-mark",
        dy: -8,
        kind: "sym",
        body: <SymbolMargin tex={pinTex(pin, att)} name={pinName(pin, att)} blocks={paper.blocks} at={pinAt} />,
      });
    }
  }

  function gapPieces(b: Block) {
    if (!core) return null;
    const arts = artsAt(b.id, pack, local);
    const notes = (b.kind === "p" || b.kind === "eq") ? notesAt(b.id, pack, local).filter((n: any) => !repeatsBlock(n, b, arts)) : [];
    const artsDrawn = (b.kind === "p" || b.kind === "eq") ? arts.filter((a) => a.type !== "forma") : [];
    const shape = arts.some((a) => a.type === "forma" && a.label);
    const nodes: ReactNode[] = [];
    if (shape) nodes.push(<ShapePill key="shape" arts={arts} />);
    notes.forEach((n: any, i: number) => nodes.push(
      <Boundary key={`n-${n.block_id}-${n.sent_index}-${n.kind || "n"}-${i}`} name="gap"><GapView note={n} self={String(paper.corpusid ?? "")} onOpen={onOpenPaper} /></Boundary>,
    ));
    artsDrawn.forEach((a, i) => nodes.push(
      <Boundary key={`a-${b.id}-${i}`} name="gap"><GapView art={a} self={String(paper.corpusid ?? "")} onOpen={onOpenPaper} /></Boundary>,
    ));
    if (wide) {
      nodes.forEach((node, i) => side.push({ id: `g-${b.id}-${i}`, anchor: `[data-blk="${b.id}"]`, body: node }));
      return null;
    }
    return nodes;
  }

  const layoutKey = `${reading ? 1 : 0}|${symPin}|${pack ? 1 : 0}|${side.map((n) => n.id).join(",")}`;

  return (
    <div className="folio" data-mode={reading ? "read" : "scan"}>
      {showNav && (
        <nav className="toc" aria-label="Contents">
          {model.toc.length > 0 && (
            <>
              <Cap>Contents</Cap>
              <ol>
                {model.toc.map((t) => {
                  const on = active === `sec-${t.id}`;
                  return (
                    <li key={t.id} className={`${t.level > 1 ? "sub" : ""}${on ? " is-on" : ""}`}>
                      <a href={`#sec-${t.id}`} aria-current={on ? "location" : undefined} onClick={(e) => { e.preventDefault(); toSection(t.id); }}>
                        <span className="n">{t.num}</span>
                        <span className="t">{t.label}</span>
                      </a>
                    </li>
                  );
                })}
              </ol>
              <div className="prog" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`Read ${pct}%`}>
                <span style={{ ["--p" as string]: String(prog) }} />
              </div>
            </>
          )}
          {showMini && (
            <Boundary name="minimap">
              <ReadMinimap papers={map?.papers || []} edges={map?.edges || []} layout={map?.layout || null} explore={explore} openId={openId} onOpen={(id) => onOpenPaper?.(id, "salto desde el minimapa")} atlasCtx={atlasCtx} />
            </Boundary>
          )}
          <p className="colo">Paper data: <a href="https://www.semanticscholar.org/" target="_blank" rel="noreferrer">Semantic Scholar</a></p>
        </nav>
      )}
      <article key={mountKey(paper)} ref={art} lang={paperLang(paper)} className={`art paper sec${reading ? " is-read" : ""}`} onTouchStart={() => (touched.current = Date.now())} onMouseOver={onOver} onMouseOut={onOut} onFocus={onOver} onBlur={onOut} onClick={onClick}>
        <Boundary name="header">
          <header className="ah paper-head">
            <div className="ah-bar">
              {metaBits.length > 0 && (
                <div className="ah-meta">
                  {metaBits.map((bit) => <span key={bit.key} className={bit.tnum ? "tnum" : undefined}>{bit.text}</span>)}
                </div>
              )}
              {core && paper.full && (
                <Segmented
                  label="Mode"
                  value={reading ? "read" : "scan"}
                  onChange={(v) => setReading(v === "read")}
                  options={[{ value: "scan", label: "Scan" }, { value: "read", label: "Read" }]}
                />
              )}
            </div>
            <h1>{polishText(paper.title)}</h1>
            {authors && <p className="ah-auth">{authors}</p>}
            <p className="ah-links">
              {paper.arxivId && <a href={`https://arxiv.org/abs/${paper.arxivId}`} target="_blank" rel="noreferrer">arXiv</a>}
              {pdfHref && <a href={pdfHref} target="_blank" rel="noreferrer">PDF</a>}
              {paper.arxivId && <button type="button" className="bib" data-bibtex={bibtex(paper)} data-copy={bibtex(paper)} data-copied="bib" title="Copy the arXiv BibTeX record">{copied === "bib" ? "Copied" : "BibTeX"}</button>}
              {!paper.arxivId && paper.corpusid != null && (remote?.status === "abstract_only" || remote?.status === "failed" || remote?.stage === "abstract_only") && <a href={`https://www.semanticscholar.org/paper/${paper.corpusid}`} target="_blank" rel="noreferrer">Semantic Scholar</a>}
            </p>
            <div className="ah-prov">
              {!paper.arxivId && <Prov kind="paper" text={`corpus:${paper.corpusid ?? ""}`} />}
              {!paper.full && !remote && <Prov kind="curado" text="abstract only in this burst" />}
              {remote?.stage === "stub" && <Prov kind="curado" text="reading sections…" />}
              {(remote?.status === "abstract_only" || remote?.stage === "abstract_only") && <Prov kind="curado" text="abstract only" />}
            </div>
            {quote && (
              <blockquote className="ah-quote">
                <Prov kind="paper" text="Abstract" />
                «{quote}»
              </blockquote>
            )}
            {core && !reading && !undrawn && paper.full && !hasConclusion(paper.blocks) && <Notice kind="absence">No conclusion section.</Notice>}
            {remote?.source === "ocr" && <Notice kind="absence">Read by OCR: equations may contain errors.</Notice>}
            {paper.license && <p className="license">{paper.license}</p>}
            {paper.authorNotes?.length > 0 && (
              <details className="author-notes"><summary>Author notes</summary>{paper.authorNotes.map((n: string, i: number) => <p key={i}>{polishText(n)}</p>)}</details>
            )}
            {showCrops && remote && paper.corpusid != null && /^\d+$/.test(String(paper.corpusid)) && <CropStrip id={String(paper.corpusid)} />}
          </header>
        </Boundary>
        {undrawn && <Notice kind="absence">{`Missing: ${faltaText(remote?.reason)}`}</Notice>}
        {undrawn && pdfHref && <iframe className="source-pdf" title="Paper PDF" src={pdfHref} />}
        {undrawn && !pdfHref && honest && <p className="ah-links"><a href={honest} target="_blank" rel="noreferrer">No PDF in the reader, on arXiv, or as an open-access PDF. The record is here.</a></p>}
        {undrawn && core && askBox("slot", abstractId, "Abstract")}
        {!undrawn && pdfPagesOnly(paper.blocks) && <Notice kind="absence">This e-print has no text: the pages are inserted from a PDF.</Notice>}
        {!undrawn && !abstractId && core && !reading && askBox("slot", "", sectionLabel)}
        {!undrawn && rows}
        <footer className="paper-foot">
          <p>Text, equations, figures, and tables are the arXiv e-print{paper.arxivId ? ` ${paper.arxivId}` : ""}, converted from LaTeX without summarizing or paraphrasing. Anything that is not from the paper carries a provenance mark.</p>
        </footer>
        {pop && <Boundary name="popover" resetKeys={[pop.key]}><Popover pop={pop} paper={paper} model={model} content={content} core={core} pack={pack} onOpen={onOpenPaper} /></Boundary>}
      </article>
      {wide && <Margin notes={side} layoutKey={layoutKey} />}
      {companion && <Companion offer={offer} target={point} onAnswer={() => setOffer(null)} onHide={() => onHideCompanion?.()} />}
    </div>
  );
}
