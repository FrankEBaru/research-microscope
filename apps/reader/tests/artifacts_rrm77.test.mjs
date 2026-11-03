import test from "node:test";
import assert from "node:assert/strict";

import { collectV2, matrixOf, polishCard, scaleOf, stepsOf } from "../src/lib/artifacts.js";
import { displayTex } from "../src/lib/backend.js";

const PE_PLAIN = String.raw`\text{PE}_{(pos,2i)}=\sin\left(\frac{pos}{10000^{\frac{2i}{d}}}\right)\\\text{PE}_{(pos,2i+1)}=\cos\left(\frac{pos}{10000^{\frac{2i}{d}}}\right)`;

const GS_ALG = String.raw`\begin{appendix}
\section{Optimization and Densification Algorithm}
Our optimization and densification algorithms are summarized in Algorithm \ref{alg:optimization}.
\begin{algorithm}[!h]
\caption{Optimization and Densification\\
$w$, $h$: width and height of the training images}
\label{alg:optimization}
\begin{algorithmic}
\State $M \gets$ SfM Points \Comment{Positions}
\State $S, C, A \gets$ InitAttributes() \Comment{Covariances, Colors, Opacities}
\State $i \gets 0$ \Comment{Iteration Count}
\While{not converged}
\State $V, \hat{I} \gets$ SampleTrainingView() \Comment{Camera $V$ and Image}
\State $I \gets$ Rasterize($M$, $S$, $C$, $A$, $V$) \Comment{Alg.~\ref{alg:rasterize}}
\State $L \gets Loss(I, \hat{I}) $ \Comment{Loss}
\State $M$, $S$, $C$, $A$ $\gets$ Adam($\nabla L$) \Comment{Backprop \& Step}
\end{algorithmic}
\end{algorithm}
\end{appendix}`;

const SPEC = String.raw`\newcommand{\COMMENTLLAMA}[1]{{\color{darkgreen} $\triangleright$ {#1}}}
\begin{algorithm}
\caption{SpeculativeDecodingStep}
\label{alg:sample_with_approx}
\begin{algorithmic}
\STATE \COMMENTLLAMA{Sample $\gamma$ guesses from $M_q$.}
\FOR{$i=1$ {\bfseries to} $\gamma$}
\STATE $q_i(x) \gets M_q(prefix + [x_1])$
\STATE $x_i \sim q_i(x)$
\ENDFOR
\STATE \COMMENTLLAMA{Run $M_p$ in parallel.}
\STATE $p_1(x) \gets M_p(prefix)$
\end{algorithmic}
\end{algorithm}`;

const GPTQ = String.raw`\begin{algorithm}[H]
\centering
\caption{Quantize $\mathbf{W}$ given inverse Hessian $\mathbf{H}^{-1} = (2 \mathbf{X} \mathbf{X}^\top + \lambda \mathbf{I})^{-1}$ and blocksize $B$.}
\label{alg:gptq}
\begin{algorithmic}
\STATE $\mathbf{Q} \gets \mathbf{0}_{d_\text{row} \times d_\text{col}}$ \quad \COMMENT{quantized output}
\STATE $\mathbf{E} \gets \mathbf{0}_{d_\text{row} \times B}$ \quad \COMMENT{block quantization errors}
\STATE $\mathbf{H}^{-1} \gets \text{Cholesky}(\mathbf{H}^{-1})^\top$ \COMMENT{Hessian inverse information}
\FOR {$i = 0, B, 2B, \dots$}
\STATE $\mathbf{W}_{:, (i + B):} \gets \mathbf{W}_{:, (i + B):} - \mathbf{E} \cdot \mathbf{H}^{-1}$ \COMMENT{update all remaining weights}
\ENDFOR
\end{algorithmic}
\end{algorithm}`;

test("3DGS pasos drops comments and sits on the density-control section", () => {
  const parsed = stepsOf(GS_ALG);
  assert.ok(parsed);
  assert.match(parsed.title, /Optimization and Densification/);
  assert.equal(parsed.steps.some((line) => /\\Comment|\\ref|\\centering/.test(line)), false);
  assert.ok(parsed.steps.some((line) => /SfM Points/.test(line)));
  assert.ok(parsed.steps.length >= 2);
  const rows = [
    { id: "h5", kind: "h", level: 1, text: "Optimization with Adaptive Density Control of 3D Gaussians" },
    { id: "p5", kind: "p", text: "We adaptively control the density of Gaussians." },
    { id: "h8", kind: "h", level: 1, text: "Discussion and Conclusions" },
    { id: "b140", kind: "p", raw: true, text: GS_ALG },
  ];
  const pack = collectV2(rows);
  const card = pack.artifacts.find((item) => item.type === "pasos");
  assert.ok(card);
  assert.equal(card.block_id, "p5");
  assert.equal(card.steps.some((line) => /\\Comment|\\ref\b/.test(line)), false);
});

test("con_sin quote is the sentence that names Q, K and V", () => {
  const rows = [
    { id: "hft", kind: "h", level: 1, text: "Fine-tuning" },
    { id: "bad", kind: "p", text: "They are fine-tuned by randomly initializing a softmax classifier on top of the pretrained model so that the gradient propagates through the whole network." },
    { id: "hatt", kind: "h", level: 1, text: "Attention" },
    { id: "eq", kind: "eq", latex: String.raw`Attention(Q, K, V) = \operatorname{softmax}(\frac{QK^T}{\sqrt{d}}) V \label{eq:binom}`, label: "eq:binom" },
    { id: "where", kind: "p", text: String.raw`where \(Q\) is a matrix of \(n_q\) query vectors, \(K\) and \(V\) both contain \(n_k\) keys and values, and \(d\) is a scaling factor.` },
  ];
  const pack = collectV2(rows);
  const card = pack.artifacts.find((item) => item.type === "con_sin");
  assert.ok(card);
  assert.match(card.quote, /scaling factor/);
  assert.match(card.quote, /\$Q\$/);
  assert.equal(/gradient propagates/.test(card.quote), false);
  assert.equal(/\\\(/.test(card.quote), false);
});

test("plain d in 10000^{2i/d} draws the PE grid; nearby tex does not", () => {
  const drawn = matrixOf(PE_PLAIN);
  assert.ok(drawn);
  assert.equal(drawn.d, 64);
  assert.equal(drawn.illustrative, true);
  assert.equal(matrixOf(String.raw`\sin(pos/10000^{2i/d_k})+\cos(pos/10000^{2i/d_k})`), null);
  assert.equal(matrixOf(String.raw`\sin(pos/10000^{\frac{i}{d}})+\cos(pos/10000^{\frac{i}{d}})`), null);
  assert.equal(matrixOf(String.raw`\sin(pos/100^{\frac{2i}{d}})+\cos(pos/100^{\frac{2i}{d}})`), null);
  const numbered = matrixOf(String.raw`d=32 \sin(pos/10000^{2i/d}) \cos(pos/10000^{2i/d})`);
  assert.ok(numbered);
  assert.equal(numbered.illustrative, false);
  assert.equal(numbered.d, 32);
  const rows = [
    { id: "h", kind: "h", level: 1, text: "Positional Encoding (PE)" },
    { id: "e1", kind: "eq", latex: String.raw`\text{PE}_{(pos,2i)}=\sin(pos/10000^{\frac{2i}{d}})` },
    { id: "e2", kind: "eq", latex: String.raw`\text{PE}_{(pos,2i+1)}=\cos(pos/10000^{\frac{2i}{d}})` },
  ];
  const card = collectV2(rows).artifacts.find((item) => item.type === "matriz");
  assert.ok(card);
  assert.equal(card.block_id, "e1");
  assert.equal(displayTex("{2}\n\\text{PE}_{(pos,2i)}").startsWith("\\text"), true);
});

test("speculative and GPTQ steps drop comment macros, centering, and nested captions", () => {
  const spec = stepsOf(SPEC);
  assert.ok(spec);
  assert.match(spec.title, /SpeculativeDecodingStep/);
  assert.equal(spec.steps.some((line) => /COMMENT/.test(line)), false);
  assert.ok(spec.steps.some((line) => /M_q/.test(line)));
  const gptq = stepsOf(GPTQ);
  assert.ok(gptq);
  assert.match(gptq.title, /Quantize/);
  assert.match(gptq.title, /blocksize/);
  assert.equal(/\\centering|\\caption|\\COMMENT/.test(`${gptq.title} ${gptq.steps.join(" ")}`), false);
  assert.ok(gptq.steps.length >= 2);
  assert.ok(gptq.steps.some((line) => /Cholesky/.test(line)));
});

test("Swin QK^T/sqrt{d} draws con_sin; a Gaussian sigma ratio does not", () => {
  const swin = String.raw`\text{Attention}(Q, K, V) = \text{SoftMax}(QK^T/\sqrt{d}+B)V`;
  const drawn = scaleOf(swin);
  assert.ok(drawn);
  assert.match(drawn.withLabel, /√d/);
  const pack = collectV2([
    { id: "h", kind: "h", level: 1, text: "Swin" },
    { id: "eq", kind: "eq", latex: swin },
    { id: "why", kind: "p", text: "Softmax of Q and K over sqrt d keeps V from peaking." },
  ]);
  assert.ok(pack.artifacts.some((item) => item.type === "con_sin"));
  const vdm = collectV2([
    { id: "h", kind: "h", level: 1, text: "Posterior" },
    { id: "b108", kind: "eq", latex: String.raw`q=\mathcal{N}(\boldsymbol{\mu},\sigma^2),\quad \sigma^2_s/\sigma^2_t` },
    { id: "b161", kind: "eq", latex: String.raw`\boldsymbol{\mu}=\frac{\alpha_s^{2}\sigma^{2}_t/\sigma^2_s-\alpha_{t}^{2}}{\sigma^{2}_{t}}` },
  ]);
  assert.equal(vdm.artifacts.some((item) => item.type === "con_sin"), false);
  const ln = collectV2([
    { id: "h", kind: "h", level: 1, text: "Layer norm" },
    { id: "eq", kind: "eq", latex: String.raw`y=(x-\mu)/\sigma` },
  ]);
  assert.ok(ln.artifacts.some((item) => item.type === "con_sin" && item.preferScale));
});

test("stray macros leave forma, casos, matriz and supuesto text", () => {
  assert.equal(polishCard(String.raw`see \eqref{eq:a} and \label{eq:a} \hypertarget{h}{kept}`), "see and kept");
  const rows = [
    { id: "h", kind: "h", level: 1, text: "Shapes" },
    { id: "e", kind: "eq", latex: String.raw`\mathbf{x}\in \mathbb{R}^{N \times 1}` },
    { id: "c", kind: "eq", latex: String.raw`y=\begin{cases} q \eqref{eq:c}, & |q| \leq q^{max} \\ 0, & \text{otherwise} \end{cases}` },
    { id: "s", kind: "p", text: String.raw`assuming that \(x\) equals \eqref{eq:a}.` },
  ];
  const pack = collectV2(rows);
  const forma = pack.artifacts.find((item) => item.type === "forma");
  const casos = pack.artifacts.find((item) => item.type === "casos");
  assert.ok(forma);
  assert.match(forma.label, /N × 1/);
  assert.ok(casos);
  assert.equal(casos.branches.some((row) => /eqref/.test(`${row.expr} ${row.cond}`)), false);
  assert.match(pack.notes[0].note, /\$x\$/);
  assert.equal(/\\eqref|\\\(/.test(pack.notes[0].note), false);
});
