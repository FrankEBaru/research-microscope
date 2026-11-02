"use client";
import { useEffect, useMemo, useRef, useState } from "react";
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
import { resolveCite } from "@/lib/path.js";
import { citeName } from "@/lib/layout.js";
import AskBox from "./AskBox";

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
import { Boundary } from "./faults";
import type { AtlasCtx } from "./screens/types";

export { plainOf } from "./paper/inline";
export { GapView } from "./paper/GapNotes";

/* ---------- utilidades ---------- */
const countNotes = (inls: Inline[]): number =>
  (inls || []).reduce((n, x) => n + (x.t === "note" ? 1 : Array.isArray(x.c) ? countNotes(x.c) : 0), 0);

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
      return <span data-pop={`m|${ctx.block}|${ctx.sent}|${token}`} data-tex={x.v}><Tex tex={x.v} display={false} syms={ctx.syms} /></span>;
    }
    case "em": return <em><Inlines inls={x.c} ctx={ctx} /></em>;
    case "strong": return <strong><Inlines inls={x.c} ctx={ctx} /></strong>;
    case "span": return <Inlines inls={x.c} ctx={ctx} />;
    case "code": return <code>{x.v}</code>;
    case "link": {
      if (x.href.startsWith("#")) {
        const lab = x.href.slice(1), shown = ctx.xref?.[lab];
        const raw = plainOf(x.c);  // pandoc deja «[etiqueta]» cuando no resuelve la referencia
        return <a href={x.href} className="xref" data-xref={lab} {...(ctx.figs?.has(lab) ? { "data-pop": `f|${lab}`, tabIndex: 0 } : {})}>{shown && (raw === `[${lab}]` || raw === lab) ? shown : <Inlines inls={x.c} ctx={ctx} />}</a>;
      }
      return <a href={x.href} target="_blank" rel="noreferrer"><Inlines inls={x.c} ctx={ctx} /></a>;
    }
    case "cite": {
      const lab = x.keys.map((k: string) => ctx.refLabels?.[k] ?? ctx.refIndex[k] ?? k);
      return <span className="cite" tabIndex={0} data-pop={`c|${x.keys.join(",")}`}>[{lab.join("; ")}]</span>;
    }
    case "note": {
      const n = ++ctx.counter.n;
      return <sup className="fn" tabIndex={0} data-pop={`n|${n}`}>{n}</sup>;
    }
    case "ref": {
      const label = x.label || "";
      let text = refText(x, ctx.xref);
      if (/(?:figure|fig\.|table|tab\.|section|sec\.|equation|eq\.|appendix|figura|tabla|sección|ecuación|apéndice)\s*~?\s*$/i.test(prev) && /^(Figura|Tabla|Sección|Apéndice|ecuación)\s+/.test(text)) {
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

/** El LaTeX a veces pega las notas de autoría al nombre. En pantalla queda solo la persona. */
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
  if (use.length > 4) return `${use.slice(0, 3).join(", ")} y ${use.length - 3} más`;
  return use.join(", ");
}

export function mountKey(paper: Paper) {
  if (!paper.stage || paper.stage === "stub") return "stub";
  return paper.upgraded_from ? "body-up" : "body";
}

/* ---------- vista principal ---------- */
export default function PaperView({ paper, content, focus, companion, onHideCompanion, remote, showInstrument = true, showCrops = true, core = false, burstIds, map, explore, openId, onOpenPaper, onPromote, atlasCtx }: { paper: Paper; content: any; focus?: string; companion?: boolean; onHideCompanion?: () => void; remote?: { status?: string; stage?: string; reason?: string; source?: string; pdf?: boolean; oa_pdf?: string; arxiv?: string } | null; showInstrument?: boolean; showCrops?: boolean; core?: boolean; burstIds?: string[]; map?: { papers: any[]; edges: any[]; layout: any } | null; explore?: { nodes?: any[]; edges?: any[] } | null; openId?: string; onOpenPaper?: (id: string, why: string) => void; onPromote?: () => void; atlasCtx?: AtlasCtx }) {
  const art = useRef<HTMLElement>(null);
  const [pop, setPop] = useState<PopState>(null);
  const [pack, setPack] = useState<any>(null);
  const [symHot, setSymHot] = useState("");
  const [symPin, setSymPin] = useState("");
  const [reading, setReading] = useState(false);
  const [left, setLeft] = useState("");
  const [hold, setHold] = useState("");
  const prevSec = useRef("");
  const timer = useRef<any>(null);
  const [active, setActive] = useState<string>("");
  const tracker = useRef(createTracker());
  const [offer, setOffer] = useState<Offer | null>(null);
  const [point, setPoint] = useState<string | null>(null); // bloque al que el compañero señala (se suelta solo)
  useEffect(() => { if (!point) return; const el = document.getElementById(point); el?.classList.remove("flash"); void el?.offsetWidth; el?.classList.add("flash"); const t = setTimeout(() => setPoint(null), 12000); return () => clearTimeout(t); }, [point]);
  useEffect(() => { if (companion && focus) setPoint(`blk-${focus}`); }, [focus, companion, paper.arxivId]);
  const [breakdown, setBreakdown] = useState<string | null>(null); // bloque `eq` cuyo desglose está abierto
  useEffect(() => { tracker.current.reset(); setOffer(null); }, [paper.arxivId, paper.stage, paper.upgraded_from, companion]);

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
    const toc: { id: string; label: string; level: number }[] = [];
    let h = [0, 0, 0], cur = "", fig = 0, tab = 0, app = false;
    const xref: Record<string, string> = {}, target: Record<string, string> = {};
    const letter = (n: number) => String.fromCharCode(64 + n);
    const figN: Record<string, number> = {}, tabN: Record<string, number> = {};
    const walk = (inls: Inline[]) => (inls || []).forEach((x) => { if (x.t === "note") notes.push({ blocks: x.blocks }); else if (Array.isArray(x.c)) walk(x.c); });
    for (const b of paper.blocks) {
      byId[b.id] = b; noteBase[b.id] = notes.length;
        if (b.kind === "h" && b.unnumbered) {
        cur = ""; toc.push({ id: b.id, label: polishText(plainOf(b.inlines)), level: 1 });
        if (/^(appendix|ap[ée]ndice)/i.test(plainOf(b.inlines))) { app = true; h = [0, 0, 0]; }
      }
      else if (b.kind === "h" && b.level <= 3) {
        if (b.number != null) cur = String(b.number);
        else {
          h[b.level - 1]++; for (let j = b.level; j < 3; j++) h[j] = 0;
          cur = h.slice(0, b.level).map((n, i) => (app && i === 0 ? letter(n) : n)).join(".");
        }
        nums[b.id] = cur;
        if (b.label) { xref[b.label] = `${app ? "Apéndice" : "Sección"} ${cur}`; target[b.label] = `sec-${b.id}`; }
        if (b.level <= 2) toc.push({ id: b.id, label: `${cur} ${polishText(plainOf(b.inlines))}`, level: b.level });
      }
      secOf[b.id] = cur;
      if (b.kind === "fig") { figN[b.id] = ++fig; if (b.label) { xref[b.label] = `Figura ${fig}`; byLabel[b.label] = b; figs.add(b.label); } }
      if (b.kind === "eq") {
        const tg = /\\tag\{([^}]*)\}/.exec(b.tex);
        (b.labels || []).forEach((l: string) => {
          if (b.number != null) xref[l] = String(l).startsWith("eq") ? `(${b.number})` : String(b.number);
          else xref[l] = tg ? `(${tg[1]})` : "ecuación";
          target[l] = `blk-${b.id}`;
        });
      }
      if (b.kind === "table") {
        b.an = analyze(b as any);
        tabN[b.id] = ++tab; if (b.label) xref[b.label] = `Tabla ${tab}`;
      }
      walk(b.inlines);
    }
    return { syms, refIndex, byId, secOf, nums, notes, noteBase, toc, figN, tabN, xref, target, byLabel, figs };
  }, [paper, att]);

  // handlers
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
      if (!has) return; // RRM-47: en core la oración solo traía la maqueta «ejemplo simulado»
    }
    if (companion) signal(key);
    const show = () => setPop({ key, rect: el.getBoundingClientRect() });
    if (key.startsWith("s|")) timer.current = setTimeout(show, 380); else show();
  };
  // el compañero solo mira repeticiones de lo que el lector ya hace con el ratón; nada sale de esta pestaña
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
  const touched = useRef(0); // con el dedo no hay «salir del elemento»: el popover se abre al tocar y se cierra al tocar fuera
  const onOut = () => { if (Date.now() - touched.current < 800) return; clearTimeout(timer.current); setPop(null); setSymHot(""); };
  useEffect(() => {
    const away = (e: TouchEvent) => { const t = e.target as HTMLElement; if (!t.closest?.("[data-pop],[data-sym],.popover")) setPop(null); };
    document.addEventListener("touchstart", away, { passive: true }); return () => document.removeEventListener("touchstart", away);
  }, []);
  const onClick = (e: React.MouseEvent) => {
    const t = e.target as HTMLElement;
    if (Date.now() - touched.current < 800 && !t.closest("[data-sym],[data-xref]")) { const el = t.closest("[data-pop]") as HTMLElement | null; if (el && !el.dataset.pop!.startsWith("s|")) setPop({ key: el.dataset.pop!, rect: el.getBoundingClientRect() }); }
    const sym = t.closest("[data-sym],[data-tex]") as HTMLElement | null;
    if (core && sym) {
      const mark = sym.dataset.sym ? `id:${sym.dataset.sym}` : sym.dataset.tex ? `tex:${sym.dataset.tex.replace(/\s+/g, "")}` : "";
      if (mark) { setSymPin((cur) => (cur === mark ? "" : mark)); return; }
    }
    if (!core && sym && att) { const s = att.symbols.find((y: any) => y.id === sym.dataset.sym); if (s) goTo(s.def.anchor.blockId); return; }
    const xr = t.closest("[data-xref]") as HTMLElement | null;
    if (xr) { e.preventDefault(); const el = document.getElementById(model.target[xr.dataset.xref!] || xr.dataset.xref!); el?.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
    const cite = t.closest("[data-pop]") as HTMLElement | null;
    if (core && cite?.dataset.pop?.startsWith("c|")) {
      const keys = cite.dataset.pop.slice(2).split(",");
      const hit = keys.map((key) => resolveCite(key, paper.citeMap)).find(Boolean);
      if (hit && onOpenPaper) { onOpenPaper(hit, "cita en el paper"); return; }
      setPop({ key: cite.dataset.pop, rect: cite.getBoundingClientRect() });
      return;
    }
    const cp = t.closest("[data-copy]") as HTMLElement | null;
    if (cp) { const old = cp.textContent; navigator.clipboard?.writeText(cp.dataset.copy!); cp.textContent = "copiado"; setTimeout(() => (cp.textContent = old), 1200); }
  };
  const esc = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const symsInTex = (tex: string): Sym[] => (att ? att.symbols : []).filter((y: Sym) => new RegExp(`(^|[^A-Za-z\\\\^_])${esc(y.latex)}`).test(tex));
  // permanencia: una ecuación completa en pantalla y sin scroll durante DWELL ms -> una oferta (no interrumpe: la acepta o no el lector)
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
  // RRM-48: en scan casi no hay encabezados (2 de 28 en Vaswani) y el índice no iba a ningún lado.
  // Si la sección no está pintada, pasa a «Leer» y baja a ella después del render.
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
    if (!core) return;
    if (prevSec.current && prevSec.current !== active) setLeft(prevSec.current);
    prevSec.current = active;
  }, [active, core]);

  const instAfter = att?.instrument.claim.anchor.blockId;
  const authors = authorLine(paper.authors || []);
  const scan = core && !reading ? scanIds(paper.blocks) : null;
  const firstHead = (paper.blocks || []).find((b) => b.kind === "h");
  const sectionNow = active.startsWith("sec-") ? (paper.blocks || []).find((b) => b.kind === "h" && b.id === active.slice(4)) : firstHead;
  const sectionLabel = sectionNow ? plainOf(sectionNow.inlines) : "inicio";
  const abstractId = (paper.blocks || []).find((b) => b.kind === "p" && b.abs)?.id || "";
  const nameOf = (id: string, section?: string) => citeName((map?.papers || []).find((item) => paperKey(item) === String(id)), section);
  const askBox = core ? (
    <Boundary name="askbox"><div className="ask-slot">
      {hold
        ? <AskBox sectionLabel="la sección que cerraste" ids={burstIds} focusId={paper.corpusid != null ? String(paper.corpusid) : ""} onOpen={onOpenPaper} onPromote={onPromote} onName={nameOf} closed onSkip={() => { setHold(""); setLeft(""); }} />
        : <AskBox sectionLabel={sectionLabel} ids={burstIds} focusId={paper.corpusid != null ? String(paper.corpusid) : ""} onOpen={onOpenPaper} onPromote={onPromote} onName={nameOf} />}
    </div></Boundary>
  ) : null;
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

  return (
    <div className="paper-layout">
      {core && (map || (explore?.nodes || []).length > 0) && <Boundary name="minimap"><ReadMinimap papers={map?.papers || []} edges={map?.edges || []} layout={map?.layout || null} explore={explore} openId={openId} onOpen={(id) => onOpenPaper?.(id, "salto desde el minimapa")} atlasCtx={atlasCtx} /></Boundary>}
      {model.toc.length > 0 && (
        <nav className="toc" aria-label="Secciones">
          {model.toc.map((t) => (
            <a key={t.id} href={`#sec-${t.id}`} className={`toc-${t.level} ${active === `sec-${t.id}` ? "on" : ""}`}
              onClick={(e) => { e.preventDefault(); toSection(t.id); }}>{t.label}</a>
          ))}
        </nav>
      )}
      <article key={mountKey(paper)} ref={art} className={`paper${reading ? " is-read" : ""}`} onTouchStart={() => (touched.current = Date.now())} onMouseOver={onOver} onMouseOut={onOut} onFocus={onOver} onBlur={onOut} onClick={onClick}>
        <Boundary name="header"><header className="paper-head">
          <div className="chips">
            <ProvChip kind="paper" text={paper.arxivId ? `arXiv:${paper.arxivId}` : `corpus:${paper.corpusid ?? ""}`} />
            {!paper.full && !remote && <ProvChip kind="curado" text="solo abstract en esta ráfaga" />}
            {remote?.stage === "stub" && <span className="chip chip-curado">leyendo secciones…</span>}
            {(remote?.status === "abstract_only" || remote?.stage === "abstract_only") && <span className="chip chip-curado">solo abstract: sin LaTeX ni PDF usable</span>}
          </div>
          <h1>{polishText(paper.title)}</h1>
          {core && paper.full && <p className="meta"><button type="button" className="link" onClick={() => setReading((v) => !v)}>{reading ? "Volver al scan" : "Leer"}</button></p>}
          {core && !reading && !hasConclusion(paper.blocks) && <p className="muted">No encontré una sección de conclusión.</p>}
          {core && left && !hold && <p className="ask-offer">Cerraste una sección. <button type="button" className="link" onClick={() => setHold(left)}>Escribir</button> <button type="button" className="link" onClick={() => setLeft("")}>Seguir</button></p>}
          {!abstractId && askBox}
          {undrawn && <p className="fail-reason">Falta: {faltaText(remote?.reason)}</p>}
          {undrawn && pdfHref && <iframe className="source-pdf" title="PDF del paper" src={pdfHref} />}
          {undrawn && !pdfHref && honest && <p className="fail-reason"><a href={honest} target="_blank" rel="noreferrer">No hay PDF en el lector, ni en arXiv, ni un openAccessPdf. La ficha está aquí.</a></p>}
          <p className="authors">{authors}</p>
          <p className="meta">{paper.date?.slice(0, 4)}{paper.arxivId && <> · <a href={`https://arxiv.org/abs/${paper.arxivId}`} target="_blank" rel="noreferrer">ver original en arXiv</a></>}{paper.full && paper.arxivId && <> · <a href={`https://arxiv.org/pdf/${paper.arxivId}`} target="_blank" rel="noreferrer">PDF</a></>}{(remote?.status === "abstract_only" || remote?.status === "failed" || remote?.stage === "abstract_only") && !paper.arxivId && paper.corpusid != null && <> · <a href={`https://www.semanticscholar.org/paper/${paper.corpusid}`} target="_blank" rel="noreferrer">Semantic Scholar</a></>}{paper.arxivId && <> · <button className="link bib" data-bibtex={bibtex(paper)} data-copy={bibtex(paper)} title="Copiar la ficha BibTeX de arXiv">BibTeX</button></>}</p>
          {remote?.status === "failed" && <p className="fail-reason">{faltaText(remote.reason)}</p>}
          {remote?.source === "ocr" && <p className="ocr-band">leído por OCR: puede haber errores en ecuaciones</p>}
          {remote && autoSentence(paper.abstract) && <blockquote><span className="qlab">frase del abstract (automática)</span>«{polishText(autoSentence(paper.abstract))}»</blockquote>}
          {paper.license && <p className="license">{paper.license}</p>}
          {paper.authorNotes?.length > 0 && (
            <details className="author-notes"><summary>Notas de autoría del paper</summary>{paper.authorNotes.map((n: string, i: number) => <p key={i}>{polishText(n)}</p>)}</details>
          )}
          {showCrops && remote && paper.corpusid != null && /^\d+$/.test(String(paper.corpusid)) && <CropStrip id={String(paper.corpusid)} />}
        </header></Boundary>

        {pdfPagesOnly(paper.blocks) && <p className="pdf-only">Este e-print no trae el texto: las páginas vienen insertadas de un PDF.</p>}
        {paper.blocks.map((b, bi) => {
          if (scan && !scan.has(b.id)) return null;
          const ctx: Ctx = { syms: model.syms, refIndex: model.refIndex, refLabels: paper.refLabels, xref: model.xref, figs: model.figs, counter: { n: model.noteBase[b.id] }, core, block: b.id };
          let el: any = null;
          if (b.kind === "h") {
            const Tag: any = b.level === 1 ? "h2" : b.level === 2 ? "h3" : "h4";
            const num = model.nums[b.id];
            el = <Tag id={`sec-${b.id}`} data-toc className={`h-${b.level}`}>{num && <span className="num">{num}</span>}<Inlines inls={b.inlines} ctx={ctx} /></Tag>;
          } else if (b.kind === "p") {
            if (!b.abs && !visibleInlines(b.inlines)) return null;
            const nb = countNotes(b.inlines);
            const prose = (
              <div id={`blk-${b.id}`} className={`blk ${b.abs ? "abstract" : ""} ${b.raw ? "raw" : ""}`}>
                {b.abs && <div className="abs-label">Resumen</div>}
                <p>{(b.sents || [b.inlines]).map((s: Inline[], i: number) => <span key={i} className="sent" data-pop={`s|${b.id}|${i}`}><Inlines inls={s} ctx={{ ...ctx, sent: i }} /></span>)}</p>
                {b.abs && remote && paper.tldr && <p className="tldr"><span className="chip chip-simulado">generado</span> {paper.tldr}</p>}
                {nb > 0 && <ol className="notes" start={model.noteBase[b.id] + 1}>{model.notes.slice(model.noteBase[b.id], model.noteBase[b.id] + nb).map((n, i) => <li key={i} value={model.noteBase[b.id] + i + 1}><Inlines inls={n.blocks.flatMap((x: Block) => x.inlines || [])} ctx={{ ...ctx, counter: { n: 999 } }} /></li>)}</ol>}
              </div>
            );
            const stepped = core && b.raw && artsAt(b.id, pack, local).some((a) => a.type === "pasos");
            el = stepped ? <details className="raw-tex"><summary>ver LaTeX</summary>{prose}</details> : prose;
          } else if (b.kind === "eq") {
            el = (
              <div id={`blk-${b.id}`} className="eq blk" {...(core ? { "data-pop": `e|${b.id}`, tabIndex: 0 } : {})}>
                <Tex tex={eqTex(b)} display syms={model.syms} />
                <button className="copy" data-copy={b.tex} aria-label="Copiar LaTeX">LaTeX</button>
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
                <figcaption><b>Figura {model.figN[b.id]}.</b> <Inlines inls={b.caption} ctx={ctx} /> <ProvChip kind="paper" text="figura original, sin redibujar" /></figcaption>
              </figure>
            );
          } else if (b.kind === "table") {
            el = <Boundary name="table"><Table b={b} ctx={ctx} n={model.tabN[b.id]} predict={showInstrument} still={reading} /></Boundary>;
          }
          const row = (
            <Boundary key={`${b.id}-${bi}`} name="row"><div className="row">
              {el}
              {breakdown === b.id && b.kind === "eq" && (
                <aside id={`bd-${b.id}`} className="breakdown" aria-label="Desglose de la ecuación">
                  <div className="chips"><ProvChip kind="curado" text="desglose curado: símbolos y definiciones del paper, no texto generado" /></div>
                  <ul>{symsInTex(b.tex).map((y: Sym) => (
                    <li key={y.id}><span className="sym-pill" style={{ color: y.color }}><Tex tex={y.latex} /></span> <b>{y.name}</b> · <em>«<Rich text={att.symbols.find((q: any) => q.id === y.id).def.quote} />»</em> <button className="link" onClick={() => goTo(att.symbols.find((q: any) => q.id === y.id).def.anchor.blockId)}>ver dónde se define</button></li>
                  ))}</ul>
                  {showInstrument && /sqrt\{d_k\}/.test(b.tex) && <p className="small">Esta ecuación divide por √d_k: <button className="link" onClick={() => document.querySelector(".instrument")?.scrollIntoView({ behavior: "smooth", block: "start" })}>ábrelo en el instrumento</button> y compruébalo.</p>}
                  <button className="link" onClick={() => setBreakdown(null)}>cerrar</button>
                </aside>
              )}
              {showInstrument && att && b.id === instAfter && <Instrument content={att} goTo={goTo} />}
              {core && <ShapePill arts={artsAt(b.id, pack, local)} />}
              {core && b.kind === "p" && notesAt(b.id, pack, local).filter((n: any) => !repeatsBlock(n, b, artsAt(b.id, pack, local))).map((n: any, i: number) => (
                <Boundary key={`${n.block_id}-${n.sent_index}-${n.kind || "n"}-${i}`} name="gap"><GapView note={n} self={String(paper.corpusid ?? "")} onOpen={onOpenPaper} /></Boundary>
              ))}
              {core && b.kind === "p" && artsAt(b.id, pack, local).filter((a) => a.type !== "forma").map((a, i) => (
                <Boundary key={`a-${b.id}-${i}`} name="gap"><GapView art={a} self={String(paper.corpusid ?? "")} onOpen={onOpenPaper} /></Boundary>
              ))}
              {core && b.kind === "eq" && notesAt(b.id, pack, local).filter((n: any) => !repeatsBlock(n, b, artsAt(b.id, pack, local))).map((n: any, i: number) => (
                <Boundary key={`n-${n.block_id}-${n.sent_index}-${n.kind || "n"}-${i}`} name="gap"><GapView note={n} self={String(paper.corpusid ?? "")} onOpen={onOpenPaper} /></Boundary>
              ))}
              {core && b.kind === "eq" && artsAt(b.id, pack, local).filter((a) => a.type !== "forma").map((a, i) => (
                <Boundary key={`a-${b.id}-${i}`} name="gap"><GapView art={a} self={String(paper.corpusid ?? "")} onOpen={onOpenPaper} /></Boundary>
              ))}
            </div></Boundary>
          );
          if (askBox && b.id === abstractId) return <div key={`${b.id}-${bi}`}>{row}{askBox}</div>;
          return row;
        })}
        <footer className="paper-foot">
          <p>Texto, ecuaciones, figuras y tablas son los del e-print de arXiv:{paper.arxivId}, convertidos desde LaTeX sin resumir ni parafrasear. Lo que no es del paper lleva una etiqueta de procedencia.</p>
        </footer>
      </article>
      {pop && <Boundary name="popover" resetKeys={[pop.key]}><Popover pop={pop} paper={paper} model={model} content={content} core={core} pack={pack} onOpen={onOpenPaper} /></Boundary>}
      {companion && <Companion offer={offer} target={point} onAnswer={() => setOffer(null)} onHide={() => onHideCompanion?.()} />}
    </div>
  );
}
