import test from "node:test";
import assert from "node:assert/strict";
import katex from "katex";
import { displayTex } from "../src/lib/backend.js";

function renders(tex) {
  katex.renderToString(displayTex(tex), { displayMode: true, throwOnError: true, strict: "ignore" });
}

test("equations that used to stay as raw TeX render", () => {
  renders(String.raw`\overrightarrow{h}_i =& \begin{cases} (1 - \overrightarrow{z}_i) & \mbox{, if } i > 0 \\ 0 & \mbox{, if } i = 0 \end{cases}`);
  renders(String.raw`\log p(y_{}|x_{}) = \sum_{j=1}^m \nolimits \log p\left(y_{j}|y_{<j},\mbox{\boldmath{$s$}}\right)`);
  renders(String.raw`\begin{split} \mathbb{E}[L_i] & = \frac{1}{2^i} \sum_{k=0}^{i} {i\choose{k}} \left\lvert\frac{i-k}{i} - \frac{1}{2}\right\rvert \end{split}`);
  renders(String.raw`\sum_{k=0}^{i} {i\choose{k}} = \left\{\begin{array}{ll} 2^{i-1} & i~$odd$ \\ 2^{i-1} & i~$even$ \end{array}\right.`);
  renders(String.raw`N_l&:= \left\lfloor N \right\rfloor \\ b&:= \exp\left(x\right)`);
  renders(String.raw`\mbox{\boldmath{$\tilde{h}$}}_{t}= \tanh(\mbox{\boldmath{$W_{c}$}}[\mbox{\boldmath{$c$}}_{t}; \mbox{\boldmath{$h$}}_{t}])`);
  renders(String.raw`\mbox{\boldmath{$\mbox{\boldmath{$a$}}_{t}$}}`);
  renders(String.raw`\ensuremath{\mathcal{O}}\left(K_{L}\textrm{max}{(K_{f},K_{\mathcal{F}})}D^{-1/d}\right)`);
  renders(String.raw`\resizebox{0.88\linewidth}{!}{ $ \hat{\mathbf{C}} = \sum_{k} T_k $ }`);
});
