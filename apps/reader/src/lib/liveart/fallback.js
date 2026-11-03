// What the gallery shows when a widget does not mount. The explanation stays.

export function fallbackText(reasons) {
  const list = reasons || [];
  if (list.some((reason) => reason === "dead_control" || String(reason).startsWith("slop_inert"))) {
    return "A control does not move the picture, so this stays as a written explanation.";
  }
  if (list.includes("slop_unrelated")) return "The picture does not match the claim, so this stays as a written explanation.";
  if (list.includes("step_cap") || list.includes("timeout")) return "The picture took too long, so this stays as a written explanation.";
  if (list.includes("banned")) return "The picture asked for something the sandbox does not allow, so this stays as a written explanation.";
  return "The picture did not mount, so this stays as a written explanation.";
}

export const STAYS_DOWN = {
  claim: "",
  kind: "down",
  widget: {
    id: "stays-down",
    topic: "stddev",
    title: "Sigma se queda escrito",
    explain: "LayerNorm resta la media y divide entre la desviación del vector. Sigma marca el ancho de esa escala. Si el dibujo no llega, esta explicación es lo que queda.",
    questions: [
      { q: "¿Qué se está normalizando, un dato o el vector?", why: "la media y la desviación son de ese vector" },
      { q: "¿Qué ve el lector si el dibujo no monta?", why: "esta explicación, con las preguntas, sin un lienzo vacío" },
    ],
    controls: [{ id: "sigma", label: "sigma", min: 0.2, max: 3, value: 1, step: 0.1 }],
    draw: `function draw(ctx, state, t) {
  ctx.fillStyle = state.sigma > 1 ? "#c2321f" : "#0b6782";
  ctx.fillRect(48, 80, 180, 72);
}`,
  },
};
