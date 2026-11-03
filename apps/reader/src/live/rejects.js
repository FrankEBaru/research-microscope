import { knob } from "./banks.js";

const okDraw = `
function draw(ctx, state, t) {
  ctx.clearRect(0, 0, state.w, state.h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(10, 10, 20, 20);
}
`;

export const REJECTS = [
  {
    id: "net-fetch",
    kind: "banned",
    names: ["fetch", "http"],
    widget: {
      id: "net-fetch",
      topic: "stddev",
      title: "Sigma es el ancho de la nube",
      explain: "La desviación estándar es el ancho de la nube.",
      questions: [
        { q: "¿Qué cambia si subo sigma en este dibujo?", why: "la nube se abre" },
        { q: "¿Por qué sigma fija la escala de los puntos?", why: "se quita el ancho" },
      ],
      controls: [knob("sigma", "sigma", 0.25, 4, 1, 0.05)],
      draw: okDraw + "\nfetch('https://evil.example');\n",
    },
  },
  {
    id: "call-random",
    kind: "banned",
    names: ["Math.random"],
    widget: {
      id: "call-random",
      topic: "softmax_temperature",
      title: "La temperatura afila el softmax",
      explain: "La temperatura parte los logits antes del softmax.",
      questions: [
        { q: "¿Por qué bajar la temperatura concentra la masa?", why: "el softmax se afila" },
        { q: "¿Qué se está partiendo antes del softmax?", why: "los logits" },
      ],
      controls: [knob("temp", "temperatura", 0.05, 5, 1, 0.05)],
      draw: okDraw.replace("fillRect(10, 10, 20, 20)", "fillRect(10, 10, Math.random() * 20, 20)"),
    },
  },
  {
    id: "bad-range",
    kind: "shape",
    names: ["control"],
    widget: {
      id: "bad-range",
      topic: "softmax_temperature",
      title: "La temperatura afila el softmax",
      explain: "La temperatura parte los logits antes del softmax.",
      questions: [
        { q: "¿Por qué bajar la temperatura concentra la masa?", why: "el softmax se afila" },
        { q: "¿Qué se está partiendo antes del softmax?", why: "los logits" },
      ],
      controls: [knob("temp", "temperatura", 5, 1, 1, 0.05)],
      draw: okDraw,
    },
  },
  {
    id: "extra-key",
    kind: "shape",
    names: ["extra_keys"],
    widget: {
      id: "extra-key",
      topic: "stddev",
      title: "Sigma es el ancho de la nube",
      explain: "La desviación estándar es el ancho de la nube.",
      questions: [
        { q: "¿Qué cambia si subo sigma en este dibujo?", why: "la nube se abre" },
        { q: "¿Por qué sigma fija la escala de los puntos?", why: "se quita el ancho" },
      ],
      controls: [knob("sigma", "sigma", 0.25, 4, 1, 0.05)],
      draw: okDraw,
      note: "x",
    },
  },
  {
    id: "off-topic",
    kind: "shape",
    names: ["off_claim"],
    widget: {
      id: "off-topic",
      topic: "rope",
      title: "Esto no gira",
      explain: "Una frase sin la palabra que el tema exige.",
      questions: [
        { q: "¿Por qué este texto no nombra el giro?", why: "falta la marca del tema" },
        { q: "¿Qué control pide el tema de rotación?", why: "el ángulo" },
      ],
      controls: [knob("sigma", "sigma", 0.25, 4, 1, 0.05)],
      draw: okDraw,
    },
  },
];
