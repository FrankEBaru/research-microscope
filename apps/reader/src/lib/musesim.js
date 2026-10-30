// Muse Spark SIMULADO, por paper (el contrato que tendría el real: recibe pregunta + texto de UN paper y devuelve SOLO selecciones).
// No es un modelo: es una coincidencia de términos sobre las oraciones del paper, para poder construir y ver el Panorama con cualquier
// pregunta. Los «enunciados» son los términos de la pregunta (temas); el Muse real los redactaría. Todo sale rotulado «simulado».
// Con `faults` también devuelve selecciones malas a propósito (inventada, alterada, paper desconocido) para ejercitar la compuerta.
import { blockText } from "./muse.js";

const STOP = new Set("funciona funcionan sirve sirven afecta afectan significa como cual cuales cuando donde porque para pero esta este esto estos estas sobre entre desde hasta cada todo toda todos todas puede pueden hace hacen tiene tienen segun sino mucho muchos which what when where does that this with from their there about between into than then them they have been were will would could should also more most such only over other what how why the and for are but not you your can".split(" "));
const DOMAIN = new Set("model models modelo modelos language lenguaje network networks learning training paper papers method methods using used show shows results data large work approach self long handle replace replaces does make makes better best new use handles transformers sequences sequence neural deep system systems task tasks performance improve improves improvement mejora mejores usar usan".trim().split(" "));
const GLOSS = { atencion: "attention", escalado: "scaling", escala: "scaling", leyes: "laws", ley: "law", modelos: "models", modelo: "model", lenguaje: "language", entrenamiento: "training", datos: "data", computo: "compute", parametros: "parameters", traduccion: "translation", imagenes: "image", imagen: "image", vision: "vision", redes: "network", neuronales: "neural", transformadores: "transformer", perdida: "loss", rendimiento: "performance", memoria: "memory", recuperacion: "retrieval", razonamiento: "reasoning", preentrenamiento: "pretraining", aprendizaje: "learning", secuencia: "sequence", costo: "cost", eficiencia: "efficiency", secuencias: "sequence", mejora: "improve", mejores: "better", tamano: "size" };
const plain = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
export const museSimMode = () => "simulado";

/** Temas = términos de contenido de la pregunta (máx. 4). `stems` son prefijos para casar con el texto del paper. */
export function themesOf(question, strict = true) {
  const seen = new Set(), out = [];
  for (let w of plain(String(question || "")).split(/[^a-z0-9-]+/)) {
    if (w.includes("-")) w = w.split("-").sort((a, b) => b.length - a.length)[0]; // «self-attention» → «attention»: la parte que distingue
    if (w.length < 4 || STOP.has(w) || (strict && DOMAIN.has(w)) || seen.has(w)) continue;
    seen.add(w);
    const orig = (String(question).normalize("NFD").match(new RegExp(w.split("").join("[\\u0300-\\u036f]*"), "i")) || [w])[0].normalize("NFC");
    const stems = [...new Set([w, GLOSS[w]].filter(Boolean).map((x) => x.slice(0, Math.min(x.length, 6))))];
    out.push({ id: `t${out.length}`, term: orig, stems });
    if (out.length === 4) break;
  }
  return out.length || !strict ? out : themesOf(question, false); // pregunta hecha solo de palabras genéricas: se usan igual
}

const sentencesOf = (doc) => {
  const out = [];
  for (const b of doc?.blocks || []) {
    if (b.kind !== "p") continue;
    const parts = b.sents && b.sents.length ? b.sents : [b.inlines];
    for (const s of parts) {
      const t = blockText({ kind: "p", inlines: s });
      if (t.length >= 50 && t.length <= 420 && (t.match(/\$/g) || []).length <= 4) out.push({ t, abs: !!b.abs });
    }
  }
  const count = new Map(); out.forEach((s) => count.set(s.t, (count.get(s.t) || 0) + 1));
  return out.filter((s) => count.get(s.t) === 1);
};
const hits = (t, th) => { const ws = plain(t).split(/[^a-z0-9]+/); return th.stems.some((st) => ws.some((w) => w.startsWith(st))); };

/** @returns {{theme: string, paper: string, quote: string}[]} la mejor oración por tema; una oración no se reparte entre temas (cada enunciado aporta evidencia propia). */
export function simulatePaper({ themes, id, doc, faults = false }) {
  const sents = sentencesOf(doc), sel = [], used = new Set();
  const tf = (t, th) => plain(t).split(/[^a-z0-9]+/).filter((w) => th.stems.some((st) => w.startsWith(st))).length;
  for (const th of themes) {
    let best = null, bs = 0;
    for (const s of sents) {
      if (used.has(s.t)) continue;
      const own = tf(s.t, th); if (!own) continue;
      const sc = own + 0.4 * themes.filter((o) => o !== th && hits(s.t, o)).length + (s.abs ? 0.6 : 0) + (s.t.length >= 70 && s.t.length <= 260 ? 0.3 : 0);
      if (sc > bs) { bs = sc; best = s; }
    }
    if (best) { used.add(best.t); sel.push({ theme: th.id, paper: id, quote: best.t }); }
  }
  return sel;
}

/** Fallas típicas de un modelo, deterministas: una frase alterada, una inventada y un paper que no existe. */
export function faultySelections(themes, firstId, perPaper) {
  if (!themes.length) return [];
  const withSel = Object.keys(perPaper).filter((k) => perPaper[k].length).sort()[0];
  const real = withSel ? perPaper[withSel][0] : null;
  const out = [{ theme: themes[0].id, paper: firstId, quote: "Este trabajo demuestra de forma concluyente que este enfoque resuelve el problema por completo." },
    { theme: themes[0].id, paper: "0000.00000", quote: "Frase de un paper que nunca se leyó." }];
  if (real) out.push({ theme: real.theme, paper: withSel, quote: real.quote.replace(/\b(\w{4,})\b/, "$1 notably") });
  return out;
}

/** Une las selecciones por paper en enunciados (la forma que `buildPanorama` espera del backend). */
export function assemble(themes, perPaper, faults = false, firstId = "") {
  const all = Object.values(perPaper).flat().concat(faults ? faultySelections(themes, firstId, perPaper) : []);
  return themes.map((th) => ({ id: th.id, statement: `Lo que dicen los papers sobre «${th.term}»`, selections: all.filter((s) => s.theme === th.id).map(({ paper, quote }) => ({ paper, quote })) }));
}

/** Procesa los papers en paralelo, escalonados (el real también tardaría distinto por paper); avisa cada vez que termina uno. */
export async function runSimulated({ question, ids, getDoc, onPaper, latencyMs = 220, cancelled = () => false }) {
  const themes = themesOf(question);
  await Promise.all(ids.map(async (id, i) => {
    const doc = await getDoc(id);
    if (latencyMs) await new Promise((r) => setTimeout(r, latencyMs * (i + 1) * 0.6));
    if (cancelled()) return;
    onPaper(id, doc, doc ? simulatePaper({ themes, id, doc }) : null);
  }));
  return themes;
}
