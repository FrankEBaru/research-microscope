"""Corpus del banco de fidelidad (RRM-8 parte B).
Cada caso: (id, familia, tipo, tex). tipo 'display' = cuerpo dentro de \\[ \\]; 'env' = entorno completo.
Preámbulo común con macros de estilo de paper (\\newcommand, \\DeclareMathOperator, \\def)."""
import random

PREAMBLE = r"""\usepackage{amsmath,amssymb,amsfonts,mathtools,bm}
\newcommand{\dmodel}{d_{\text{model}}}
\newcommand{\R}{\mathbb{R}}
\newcommand{\norm}[1]{\left\lVert #1\right\rVert}
\DeclareMathOperator{\softmax}{softmax}
\DeclareMathOperator*{\argmax}{arg\,max}
\def\E{\mathbb{E}}
"""

H = [  # hechos a mano
 # fracciones, raíces, coeficientes
 ("frac-anid", "frac", "display", r"\frac{1}{1+\frac{1}{1+\frac{1}{1+x}}}"),
 ("frac-cfrac", "frac", "display", r"x = a_0 + \cfrac{1}{a_1 + \cfrac{1}{a_2 + \cfrac{1}{a_3}}}"),
 ("frac-dfrac", "frac", "display", r"\dfrac{\partial^2 f}{\partial x\,\partial y} = \tfrac{1}{2}\left(\dfrac{\partial f}{\partial x}+\dfrac{\partial f}{\partial y}\right)"),
 ("frac-binom", "frac", "display", r"\binom{n}{k} = \frac{n!}{k!\,(n-k)!}, \qquad \binom{n}{k}=\binom{n-1}{k-1}+\binom{n-1}{k}"),
 ("raiz-anid", "raiz", "display", r"\sqrt{1+\sqrt{1+\sqrt{1+\sqrt{x}}}}"),
 ("raiz-indice", "raiz", "display", r"\sqrt[3]{\frac{a^3+b^3}{2}} \ge \sqrt{ab}"),
 ("raiz-cuad", "raiz", "display", r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}"),
 # sumas, productos, límites
 ("suma-doble", "suma", "display", r"\sum_{i=1}^{n}\sum_{j=1}^{m} a_{ij}\, x_i y_j"),
 ("suma-substack", "suma", "display", r"\sum_{\substack{0<i<m\\ 0<j<n}} P(i,j)"),
 ("prod-euler", "suma", "display", r"\prod_{k=1}^{\infty}\left(1-\frac{1}{k^2}\right)=\frac{\sin \pi}{\pi}"),
 ("union", "suma", "display", r"\bigcup_{i\in I} A_i \subseteq \bigcap_{j\in J} B_j"),
 ("limite", "suma", "display", r"\lim_{n\to\infty}\left(1+\frac{1}{n}\right)^{n}=e"),
 # integrales
 ("int-gauss", "integral", "display", r"\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}"),
 ("int-doble", "integral", "display", r"\iint_{D} f(x,y)\,dA = \int_a^b\!\!\int_{g(x)}^{h(x)} f(x,y)\,dy\,dx"),
 ("int-cont", "integral", "display", r"\oint_{C} \vec F\cdot d\vec r = \iint_S (\nabla\times\vec F)\cdot d\vec S"),
 # matrices
 ("mat-p3", "matriz", "display", r"A=\begin{pmatrix} a_{11} & a_{12} & a_{13}\\ a_{21} & a_{22} & a_{23}\\ a_{31} & a_{32} & a_{33}\end{pmatrix}"),
 ("mat-b-det", "matriz", "display", r"\det\begin{bmatrix} 1 & x & x^2\\ 1 & y & y^2\\ 1 & z & z^2\end{bmatrix} = (y-x)(z-x)(z-y)"),
 ("mat-v", "matriz", "display", r"\begin{vmatrix} a & b\\ c & d\end{vmatrix} = ad - bc"),
 ("mat-bloque", "matriz", "display", r"M=\begin{pmatrix} A_{11} & \cdots & A_{1n}\\ \vdots & \ddots & \vdots\\ A_{m1} & \cdots & A_{mn}\end{pmatrix}"),
 ("mat-array", "matriz", "display", r"\left[\begin{array}{c|cc} 1 & 2 & 3\\ \hline 4 & 5 & 6\\ 7 & 8 & 9\end{array}\right]"),
 # casos y alineados
 ("cases", "alinear", "display", r"f(x)=\begin{cases} x^2 & \text{if } x\ge 0,\\ -x & \text{if } x<0,\\ 0 & \text{otherwise.}\end{cases}"),
 ("align-2", "alinear", "env", r"\begin{align*} f(x) &= (x+1)^2 \\ &= x^2 + 2x + 1 \\ &\ge 2x \end{align*}"),
 ("align-cols", "alinear", "env", r"\begin{align*} a &= b + c & d &= e \cdot f\\ a' &= b' & d' &= e' \end{align*}"),
 ("gather", "alinear", "env", r"\begin{gather*} x^2 + y^2 = r^2\\ \sin^2\theta + \cos^2\theta = 1 \end{gather*}"),
 ("split", "alinear", "env", r"\begin{equation*}\begin{split} (a+b)^3 &= a^3 + 3a^2 b + 3 a b^2 + b^3\\ &= \sum_{k=0}^{3}\binom{3}{k}a^{3-k}b^k \end{split}\end{equation*}"),
 ("aligned", "alinear", "display", r"\begin{aligned} \nabla\cdot\vec E &= \frac{\rho}{\varepsilon_0} \\ \nabla\times\vec B &= \mu_0\vec J + \mu_0\varepsilon_0\frac{\partial\vec E}{\partial t}\end{aligned}"),
 # llaves, flechas
 ("underbrace", "flechas", "display", r"\underbrace{a+b+\cdots+z}_{26\ \text{letters}}"),
 ("overbrace", "flechas", "display", r"\overbrace{x_1 + x_2 + \dots + x_n}^{\text{$n$ terms}} = S_n"),
 ("xarrow", "flechas", "display", r"A \xrightarrow[\text{below}]{f\circ g} B \xleftarrow{h} C"),
 ("overset", "flechas", "display", r"x \overset{\text{def}}{=} y,\quad a \stackrel{!}{=} b,\quad f\colon X\to Y"),
 # acentos y alfabetos
 ("acentos", "alfabeto", "display", r"\hat{x}\ \tilde{y}\ \bar{z}\ \vec{v}\ \dot{a}\ \ddot{b}\ \widehat{ABC}\ \widetilde{xyz}\ \overline{AB}\ \underline{CD}"),
 ("alfabetos", "alfabeto", "display", r"\mathbb{R}^n,\ \mathbb{N},\ \mathcal{L}(\theta),\ \mathfrak{g},\ \mathbf{x},\ \boldsymbol{\alpha},\ \mathsf{T},\ \mathtt{code},\ \mathrm{d}x"),
 ("griego-min", "alfabeto", "display", r"\alpha\beta\gamma\delta\epsilon\varepsilon\zeta\eta\theta\vartheta\iota\kappa\lambda\mu\nu\xi\pi\rho\varrho\sigma\tau\upsilon\phi\varphi\chi\psi\omega"),
 ("griego-may", "alfabeto", "display", r"\Gamma\Delta\Theta\Lambda\Xi\Pi\Sigma\Upsilon\Phi\Psi\Omega"),
 ("simbolos", "alfabeto", "display", r"\forall x\,\exists y:\ x\le y \ne z \approx w \propto v \sim u \simeq t \cong s \equiv r \in \notin \subset \cup \cap \infty \partial \nabla \hbar \ell"),
 # delimitadores
 ("delim-auto", "delim", "display", r"\left(\frac{a}{b}\right)\left[\sum_{i}x_i\right]\left\{\frac{1}{2}\middle|\ x\in X\right\}"),
 ("delim-angle", "delim", "display", r"\left\langle \psi\middle|\hat H\middle|\phi\right\rangle,\quad \left\lVert x\right\rVert_2,\quad \left\lfloor x\right\rfloor,\ \left\lceil y\right\rceil"),
 ("delim-big", "delim", "display", r"\Big(\Big[\Big\{ \bigg(\bigg[ \Bigg( x \Bigg)\bigg]\bigg)\Big\}\Big]\Big)"),
 # operadores
 ("oper-argmax", "operador", "display", r"\hat\theta = \operatorname*{arg\,max}_{\theta\in\Theta} \sum_{i=1}^{n}\log p(x_i\mid\theta)"),
 ("oper-macro", "operador", "display", r"\softmax(x)_i = \frac{e^{x_i}}{\sum_{j} e^{x_j}},\qquad \argmax_{x} f(x)"),
 ("oper-nombres", "operador", "display", r"\log\det A=\operatorname{tr}\log A,\quad \max_{x\in X}\min_{y}\ \sin\cos\tan\ \exp\ \ln\ \gcd\ \Pr"),
 ("texto", "operador", "display", r"x \quad\text{if } x>0 \quad\text{and}\quad y \quad \text{for all } x\in\R"),
 # espacios y puntos
 ("espacios", "simbolo", "display", r"a\,b\;c\ d\quad e\qquad f\!g \ldots \cdots \vdots \ddots"),
 ("subsup", "simbolo", "display", r"x_{i_j}^{k^2},\quad a_{ij}^{(l)},\quad \mathbf{W}^{(l)}_{\text{out}},\quad {}^{14}\!C,\quad \sum_i^{} x_i^{2^{3}}"),
 ("tag", "simbolo", "env", r"\begin{equation} E = mc^2 \tag{3.2} \end{equation}"),
 ("numerada", "simbolo", "env", r"\begin{equation} a^2 + b^2 = c^2 \end{equation}"),
 # estilo de paper
 ("paper-attn", "paper", "display", r"\mathrm{Attention}(Q,K,V)=\softmax\!\left(\frac{QK^{\top}}{\sqrt{d_k}}\right)V"),
 ("paper-mh", "paper", "display", r"W^Q_i \in \R^{\dmodel\times d_k},\quad W^O \in \R^{h d_v\times \dmodel}"),
 ("paper-lrate", "paper", "display", r"lrate = \dmodel^{-0.5}\cdot \min(step^{-0.5},\ step\cdot warmup^{-1.5})"),
 ("paper-pe", "paper", "env", r"\begin{align*} PE_{(pos,2i)} &= \sin(pos/10000^{2i/\dmodel})\\ PE_{(pos,2i+1)} &= \cos(pos/10000^{2i/\dmodel})\end{align*}"),
 ("paper-kl", "paper", "display", r"D_{\mathrm{KL}}(p\,\Vert\,q)=\sum_x p(x)\log\frac{p(x)}{q(x)}=\E_{x\sim p}\!\left[\log\frac{p(x)}{q(x)}\right]"),
 ("paper-elbo", "paper", "display", r"\log p_\theta(x)\ge \E_{q_\phi(z\mid x)}\!\left[\log p_\theta(x\mid z)\right]-D_{\mathrm{KL}}\!\left(q_\phi(z\mid x)\,\Vert\,p(z)\right)"),
 ("paper-bayes", "paper", "display", r"p(\theta\mid\mathcal{D})=\frac{p(\mathcal{D}\mid\theta)\,p(\theta)}{\int p(\mathcal{D}\mid\theta')\,p(\theta')\,d\theta'}"),
 ("paper-adam", "paper", "display", r"\theta_{t+1}=\theta_t-\frac{\eta}{\sqrt{\hat v_t}+\epsilon}\hat m_t,\quad \hat m_t=\frac{m_t}{1-\beta_1^t}"),
 ("paper-norm", "paper", "display", r"\norm{x}_p=\Big(\sum_{i=1}^n |x_i|^p\Big)^{1/p}"),
 # física / matemáticas largas
 ("fis-schr", "fisica", "display", r"i\hbar\frac{\partial}{\partial t}\Psi(\mathbf r,t)=\left[-\frac{\hbar^2}{2m}\nabla^2+V(\mathbf r,t)\right]\Psi(\mathbf r,t)"),
 ("fis-ns", "fisica", "display", r"\rho\left(\frac{\partial\mathbf v}{\partial t}+\mathbf v\cdot\nabla\mathbf v\right)=-\nabla p+\mu\nabla^2\mathbf v+\mathbf f"),
 ("mat-taylor", "fisica", "display", r"f(x)=\sum_{n=0}^{\infty}\frac{f^{(n)}(a)}{n!}(x-a)^n+R_n(x)"),
 ("mat-fourier", "fisica", "display", r"\hat f(\xi)=\int_{-\infty}^{\infty} f(x)\,e^{-2\pi i x\xi}\,dx"),
 ("mat-zeta", "fisica", "display", r"\zeta(s)=\sum_{n=1}^{\infty}\frac{1}{n^s}=\prod_{p\ \text{primo}}\frac{1}{1-p^{-s}}"),
 # sondas: comandos que KaTeX probablemente no soporta o que dependen de paquetes
 ("sonda-bm", "sonda", "display", r"\bm{x}\in\R^n,\ \bm{\Sigma}"),
 ("sonda-eqnarray", "sonda", "env", r"\begin{eqnarray*} a &=& b+c\\ d &=& e \end{eqnarray*}"),
 ("sonda-hspace", "sonda", "display", r"a\hspace{1em}b\hphantom{xx}c\vphantom{\frac12}d"),
 ("sonda-raisebox", "sonda", "display", r"x\raisebox{1ex}{$y$}z"),
 ("sonda-mathop", "sonda", "display", r"\mathop{\mathrm{Var}}\limits_{x}(f)\ \mathbin{\star}\ \mathrel{\triangleq}"),
 ("sonda-underset", "sonda", "display", r"\underset{x\in X}{\mathrm{minimize}}\ f(x)\quad \text{s.t.}\ g(x)\le 0"),
]


def _rand_expr(rng, depth=0):
    atoms = ["x", "y", "z", r"\alpha", r"\beta", r"\theta", "n", "k", "2", "3", "0.5", r"\pi", r"\sigma^2", r"\mu_i"]
    if depth >= 3 or rng.random() < 0.25:
        return rng.choice(atoms)
    a, b = _rand_expr(rng, depth + 1), _rand_expr(rng, depth + 1)
    t = rng.choice(["frac", "sqrt", "sum", "sub", "sup", "paren", "bin", "func", "int", "hat", "abs", "prod"])
    return {
        "frac": rf"\frac{{{a}}}{{{b}}}", "sqrt": rf"\sqrt{{{a}}}", "sum": rf"\sum_{{i=1}}^{{{b}}} {a}",
        "sub": rf"{{{a}}}_{{{b}}}", "sup": rf"{{{a}}}^{{{b}}}", "paren": rf"\left({a}+{b}\right)",
        "bin": rf"{a} {rng.choice(['+','-',r'\cdot',r'\times',r'\le','='])} {b}",
        "func": rf"\log\!\left({a}\right)", "int": rf"\int_0^{{{b}}} {a}\,dt", "hat": rf"\hat{{{a}}}", "abs": rf"\left|{a}\right|",
        "prod": rf"\prod_k {a}",
    }[t]


def cases(n_random=30, seed=20261029):
    rng = random.Random(seed)
    out = list(H)
    for i in range(n_random):
        out.append((f"azar-{i:02d}", "azar", "display", f"{_rand_expr(rng)} = {_rand_expr(rng)}"))
    return out
