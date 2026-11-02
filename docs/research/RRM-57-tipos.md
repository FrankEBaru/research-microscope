# RRM-57 — Tipos de artefactos y de huecos

Hay que generalizar dos pistas de Attention (`con_sin`, `matriz`) a cualquier paper de mates o computación. En 54 papers, lo que más rinde es código: una cajita de forma, un stepper de algoritmo, la escala con/sin (ya dibujada, detector más ancho) y la rama de un `cases`. Muse no hace falta para eso.

Los conteos salen de `python3 scripts/research/rrm57_tipos.py <dir>` sobre el tar `papers_parsed` (54 JSON; el ticket decía 53). **[V]** corrí el script el 2 nov 2026. Una ecuación cuenta si `kind=eq`. Las frases de supuesto, salto, atajo y algoritmo se buscan en cualquier fila. No bajé arXiv. Modal: $0.

## Lo que hay hoy

`rrm/reader/gaps.py` marca un hueco si a la ecuación le falta un token en el párrafo de al lado, y solo entonces pone pista: `matriz` si hay sen/cos y `10000`, `con_sin` si el denominador trae `\sqrt`. `apps/reader/src/lib/artifacts.js` dibuja esas dos y nada más. El porqué lo escribe Muse. Esas dos señales no salen de Attention: la rejilla también está en la DCT, y la escala también en Informer, posiciones relativas y Layer Norm.

## Artefactos

Dibujo solo si el código evalúa la fórmula o parte una estructura que ya está escrita. Si faltan datos del experimento, no se inventan barras.

### 1. forma — cajita con el tamaño

- **Duda.** «Esto es un vector, una matriz o un cubo, y de qué lado.»
- **Señal.** `\mathbb{R}^{...}` en el latex o en la prosa de la fila. Compuesta: el superíndice trae `\times`, un dígito o un `+`.
- **Datos.** Solo esa cadena. No hace falta el valor numérico de `n`.
- **Código.** El regex. Muse no: el tamaño ya está escrito.
- **Papers.** 13/54, y los 13 tienen al menos una forma compuesta. **[V]** Ids: 556999, 3104000, 3537408, 3670018, 3725815, 5633749, 11212020, 13584443, 31194450, 37925315, 52967399, 229156802, 267700687.
- **Ejemplos.** 13584443, Compressed Sensing and Associated Models: `$\mathbf{x}\in \mathbb{R}^{N \times 1}$` y `$\mathbf{\Phi} \in \mathbb{R}^{M \times N}$`. 229156802, Efficient Self-attention Mechanism: `$\mathbf{Q} \in \mathbb{R}^{L_Q \times d}$`.
- **Plantilla.** Una pastilla junto al símbolo: `N × 1`. Una por sección, la primera compuesta. `\mathbb{R}^{n}` pelado no se pastilla: el superíndice ya se lee.
- **Ruido.** Boyd (37925315) tiene muchas. Sin el tope de una por sección, la página se llena de pastillas.
- **Costo.** $0. Latencia de un regex.

### 2. pasos — el algoritmo, de a un renglón

- **Duda.** «¿En qué orden corre, y qué entra?» Hoy el algoritmo llega como un párrafo.
- **Señal.** `\begin{algorithm}` en el texto o en el latex.
- **Datos.** El cuerpo entre `\begin{algorithm}` y `\end{algorithm}`. Se parte por `\State`, `\For`, `\While`, `\KwIn`, `\;`.
- **Código.** El corte. Muse no: el pseudocódigo es del autor.
- **Papers.** 11/54. **[V]** 1114678 (BPE), 1849480 (búsqueda), 2871880 (DANN), 4650265 (XGBoost), 14876957 (PRM), 31194450 (Monte Carlo), 37925315 (Boyd), 49310446 (Neural ODE), 207178795 (LinUCB), 229156802 (Informer), 267700687 (bilevel).
- **Ejemplo.** 4650265, Basic Exact Greedy Algorithm: `\begin{algorithm} \caption{Exact Greedy Algorithm for Split Finding} ... \KwIn{$I$, instance set of current node}`.
- **Plantilla.** Un stepper: paso `k/n`, el renglón, y los `\KwIn` arriba como fijos. No se simula el algoritmo.
- **Ruido.** En Informer el algoritmo viene pegado a un párrafo que empieza en el apéndice. Hay que recortar del `\begin{algorithm}` al `\end{algorithm}`, no mostrar el párrafo entero.
- **Costo.** $0.

### 3. escala — con y sin el divisor

- **Duda.** «¿Qué cambia si quito este `\sqrt{d}` o este `\sigma`?» Es el `con_sin` de hoy, para cualquier saturación o centrado, no solo el softmax de Attention.
- **Señal.** En una ecuación: softmax (o exp) y `\sqrt` de una `d`, o `(a-\mu)` dividido entre `\sigma` (`\over\sigma`). Si la sección tiene a lo más 6 ecuaciones, también vale que una tenga el softmax y otra el `\sqrt`. El tope de 6 saca a Boyd, que junta las dos cosas en secciones enormes sin que sean la misma operación.
- **Datos.** La fórmula. El probe ilustrativo (semilla fija) solo si el dibujo con y sin divisor se ve distinto; si no, no hay dibujo. Esa prueba ya está en `compareOf`.
- **Código.** Detectar y evaluar. La frase del porqué se copia del mismo paper si aparece (en Attention está). Muse no.
- **Papers.** 4/54. **[V]** 13756489 Attention, 229156802 Informer, 3725815 posiciones relativas (`e_{ij}` entre `\sqrt{d_z}`), 8236317 Layer Norm.
- **Ejemplos.** 13756489, Scaled Dot-Product Attention: `\mathrm{Attention}(Q, K, V) = \mathrm{softmax}(\frac{QK^T}{\sqrt{d_k}})V`. El porqué, sección Background: «We suspect that for large values of $d_k$, the dot products grow large in magnitude, pushing the softmax function into regions where it has extremely small gradients. To counteract this effect, we scale the dot products by $\frac{1}{\sqrt{d_k}}$.» 8236317, Background: `\bar{a}^l_i = g^l_i / \sigma^l_i (a^l_i - \mu^l_i)`.
- **Plantilla.** Dos columnas, misma entrada. Softmax: barras con y sin el divisor (la de hoy). Layer Norm: el vector antes y después de dividir entre `\sigma`. No pasar Layer Norm por el softmax.
- **Ruido.** Bajo, porque el dibujo se cae si las dos columnas quedan iguales. Un `\sqrt` suelto en una cota (Boyd, la DCT) no entra.
- **Costo.** $0. La frase ya está en el paper; buscarla es otro regex (`gradient`, `scale`, `counteract`, `variance` en el mismo paper).

### 4. casos — cuál rama

- **Duda.** «¿Esta definición hace una cosa u otra, y cuándo?»
- **Señal.** `\begin{cases}`, o un `array` con `\text{if}` / `\mbox{if}` / `\mathrm{if}`.
- **Datos.** Cada rama y su condición, partiendo por `\\`.
- **Código.** El corte. Muse no.
- **Papers.** 8/54. **[V]** 1085798 (tráfico), 11212020 (el paso `i=0` del encoder), 11862960 (KMP), 15216093 (recorte del inversor), 18487369 (borde de la malla), 31194450 (indicador), 37925315 (indicador), 267700687 (complementariedad de Nash).
- **Ejemplo.** 15216093, Control on Local Flows Only: `\text{Constr}_{j}[q] = \begin{cases} q, & |q| \leq q_j^{max} \\ (q/|q|)q_j^{max}, & \text{otherwise} \end{cases}`.
- **Plantilla.** Dos o tres renglones. La condición en gris, la expresión en negro. Sin slider: no sabemos `q`.
- **Ruido.** El indicador `1 si predicado` (Boyd, multifidelity) es obvio. Aun así son 8 papers y el widget es una lista, no un gráfico de más.
- **Costo.** $0.

### 5. curva — la fórmula de una variable, con los números del párrafo

- **Duda.** «¿Qué forma tiene esto si muevo la variable?»
- **Señal.** Ecuación sin `\sum`, y el mismo párrafo da el número que falta, o la expresión ya es numérica. El script marca cuatro: logit con `0.5`, gauss cuyo párrafo trae `\approx`, agenda `\gamma` «set to 10», tasa con `warmup` y `4000` en el párrafo.
- **Datos.** Esos números, leídos del párrafo. Si no están, no se grafica.
- **Código.** Sustituir y evaluar. Muse no. En la prueba, Muse dijo que la tasa y la agenda de DANN ya están explicadas y que el dibujo igual ayuda (ver abajo).
- **Papers.** 4/54. **[V]** 13756489 (tasa de aprendizaje), 16982763 (logit de confianza), 2871880 (agenda `\lambda_p`), 3719281 (peso gaussiano del U-Net).
- **Ejemplos.** 2871880, CNN architectures and Training Procedure: `\lambda_p = 2/(1+\exp(-\gamma \cdot p))-1`, y en el mismo texto «where $\gamma$ was set to $10$ in all experiments». 3719281, Training: el peso con `\exp(-(d_1+d_2)^2 / 2\sigma^2)`, y «we set $w_0 = 10$ and $\sigma \approx 5$ pixels».
- **Plantilla.** Una curva, eje con el símbolo libre (`p`, `step_num`, distancia), los números del párrafo en el pie. Nada de «ilustrativo» si el número está.
- **Ruido.** Elegir mal la variable libre. Por eso la señal es estrecha: 4 papers, no «cualquier exp». La sigmoide de voltaje del paper 15216093 (`G(q^{max}, V, \delta)`) se ve como curva, pero `\delta` no está numérico en la fórmula: no entra.
- **Costo.** $0. El evaluador es lo caro en líneas, no en dólares.

### 6. rejilla — sen/cos de dos índices

- **Duda.** «¿Qué cambia de una fila a la siguiente?» Es la `matriz` de hoy, sin exigir el `10000` ni `d_model`.
- **Señal.** `sin(pos/...)` o `cos(pos/...)`, o sen/cos de un `\frac` que contiene `k` y `n`.
- **Datos.** La fórmula cerrada. Se evalúa en una retícula chica (como hoy, 32 posiciones).
- **Código.** Igual que `matrixOf`, con la señal de arriba. El pie sale de los nombres de los índices. Muse no.
- **Papers.** 2/54. **[V]** 13756489 (PE, ya dibujada) y 1195959 (DCT).
- **Ejemplo.** 1195959, Introduction: `X(k)=\alpha(k)\sum_{n=0}^{N-1} x(n)\cos\frac{k(4qn+r)p\pi}{2N}`.
- **Plantilla.** La heatmap de hoy. Cada fila es un `k` o una `i`. Leyenda con el símbolo, no «dimensión de Attention» fija.
- **Ruido.** Bajo: sen/cos de un solo ángulo (el cuadricóptero, el flujo de potencia) no trae dos índices dentro del argumento, y no entra. La frecuencia es baja; el cambio de detector es chico y cabe en el mismo PR que la escala.
- **Costo.** $0.

### 7. atajo — dos caminos que se suman o se concatenan

- **Duda.** «¿Qué se le suma a qué, o qué se concatena con el camino que viene?»
- **Señal.** En prosa: `residual connection`, `shortcut connection`, `skip connections`, o `cropped feature map`.
- **Papers.** 6/54. **[V]** 13756489, 206594692 (ResNet), 229156802, 3725815, 52281312 (VoxelMorph), 3719281 (U-Net: «a concatenation with the correspondingly cropped feature map from the contracting path»).
- **Ejemplo.** 206594692, Identity Mapping by Shortcuts: `\mathbf{y} = \mathcal{F}(\mathbf{x}, \{W_i\}) + \mathbf{x}`. El mismo paper apunta a `Fig. fig:block`.
- **Plantilla.** Dos flechas que se juntan. No la recomiendo ahora: en las 8 fuentes LaTeX el autor ya dibujó el bloque (ResNet 7 `\includegraphics`, U-Net 10, DANN 31 más 12 tikz, Neural ODE 85, XGBoost 18, bandit 12). El reader ya muestra figuras. Un segundo diagrama repite la figura.
- **Ruido.** Alto si se dispara con «residual» a secas (ruido residual, red residual). La señal de arriba es estrecha y aun así duplica la figura.
- **Costo.** $0, y no vale el widget.

### 8. campo — derivada temporal

- **Duda.** «¿Cuál es el estado y quién lo empuja?»
- **Señal.** En el latex de la ecuación: `\dot{`, `\ddot{`, o `\frac{d...}{dt}`.
- **Papers.** 5/54. **[V]** 1085798 (tráfico), 12866 (cuadricóptero), 3104000 (humanoide), 49310446 (Neural ODE: `\frac{d\mathbf{h}(t)}{dt} = f(\mathbf{h}(t), t, \theta)`), 37925315 (derivada de Lyapunov). GADGET-2 escribe la EDO dentro de un párrafo, no en `kind=eq`: el script no la cuenta.
- **Plantilla.** Tres etiquetas: estado, `d/dt`, lado derecho. Sin integrar la EDO: sin datos, la trayectoria sería inventada.
- **Ruido.** La derivada de Lyapunov no es un flujo para simular. Como caja de etiquetas, sirve; como animación, miente.
- **Costo.** $0. Después del PR corto.

### 9. objetivo — qué se minimiza y bajo qué

- **Duda.** «¿Qué elijo y qué está fijo?»
- **Señal.** `arg min` en el latex, o `s.t.` junto a un `\min` / `\text{min}`.
- **Papers.** 6/54. **[V]** 267700687, 31194450, 37925315, 44604205 (el `arg min` de NetVLAD es un vecino, no un programa), 52281312 (VoxelMorph), 3104000 (dinámica inversa, `s.t.`).
- **Ejemplo.** 3104000, Hierarchical Inverse Dynamics Solver: minimiza `\|\mathbf{v}\|^2 + \|\mathbf{w}\|^2` sujeto a desigualdades de torque y restricciones de tarea.
- **Plantilla.** Tres renglones: minimizar / sobre estas variables / sujeto a. El parse de los `aligned` de Boyd es frágil.
- **Ruido.** NetVLAD no es un programa de optimización; es «el positivo más cercano». Un detector de `arg min` lo mezcla.
- **Costo.** $0. No entra en el PR corto: mucho parse para 6 papers, uno de ellos ruidoso.

### 10. barras — una distribución sobre un índice

- **Duda.** «¿Sobre qué se reparte esta masa, y suma uno?»
- **Señal.** `softmax`, o `\exp` con `\sum` y `\frac` en la misma ecuación.
- **Papers.** 8/54. **[V]** 11212020 (NMT), 13756489, 16982763 (confianza), 229156802, 2871880 (DANN), 3725815, 37925315 (espejo entrópico), 7105713 (máxima entropía).
- **Ejemplo.** 11212020, Decoder: `\alpha_{ij} = \exp(e_{ij}) / \sum_k \exp(e_{ik})`. Los `e_{ij}` no están en el paper como números.
- **Plantilla.** No hay barras si el score es opaco (`e_{ij}`, rasgos, gradientes). Ahí el pie, en código: «suma 1 sobre el índice del `\sum`». Barras de verdad solo cuando la escala (tipo 3) hace que el dibujo cambie, o cuando la curva (tipo 5) ya se puede evaluar.
- **Ruido.** Alto si se dibujan alturas con una normal inventada. Attention ya lo hace, con leyenda «ilustrativo» y una prueba de oro. Copiarlo a NMT o a DANN no enseña el paper.
- **Costo.** $0 el pie. Un llamado a Muse para «explicar el softmax» no tiene frase que citar: el modelo, en la prueba, pidió una nota para NMT y la prosa solo dice que normalizan.

## Huecos

La nota nueva cita una frase del paper o no se escribe. No se le pide a Muse que complete un paso.

### supuesto — el autor condicionó la fórmula

- **Duda.** «¿Bajo qué condición es cierta esta cuenta?»
- **Señal.** `we assume that`, `assume that`, `assuming that`, `suppose that`, `under the assumption that`, `without loss of generality`, y a ±70 caracteres hay `$` o `\`.
- **Papers.** 18/54, 63 frases. **[V]** Leí la primera frase de cada paper en la salida del script; todas atan un símbolo o una condición. El relato «we assume that Mike has registered» (15340505) no entra: no tiene mate al lado.
- **Ejemplo.** 206594692, Residual Learning: «assuming that the input and output are of the same dimensions». 49310446, Continuous Normalizing Flows: «Assuming that $f$ is uniformly Lipschitz continuous in $\mathbf{z}$ and continuous in $t$».
- **Código.** La nota es esa frase, pegada a la siguiente ecuación de la sección. Muse no.
- **Ruido.** Una suposición de notación («suponemos que el espacio es `\mathbb{R}^m`») repite la cajita de forma. Se puede no duplicar si la frase solo presenta un `\mathbb{R}`.
- **Costo.** $0.

### salto — «se ve fácil» y el resultado ya viene en la frase

- **Duda.** El lector cree que se perdió un paso.
- **Señal.** `it is easy to see/show`, `straightforward to check/show`, `we omit the coefficient/proof`, `one can show that`, `it can be shown that`, `without loss of generality`, con mate a ±70 caracteres.
- **Papers.** 11/54. **[V]** 12866, 147227, 1085798, 1195959, 3259798, 8236317, 14124313, 14876957, 16982763, 44604205, 207178795.
- **Ejemplo.** 1195959, Generalized discrete W transform: «To simplify the problem, we omit the coefficient $\frac{1}{\sqrt N}$.» 44604205, NetVLAD: «it is easy to see that the term $e^{-\alpha\|x_i\|^2}$ cancels between the numerator and the denominator».
- **Código vs Muse.** En las 11 frases que leí, la oración ya dice el resultado (cancela, el máximo está en `K=\kappa/2`, el campo receptivo es 5×5). Repetirla en una nota no aporta. Pedirle a Muse el álgebra que falta es inventar: el sistema de notas actual lo prohíbe. No la implementaría como nota generada. El caso que sí vale es el coeficiente omitido (DCT): la nota cita la frase, porque el autor avisa que tiró un factor.
- **Costo.** $0 si es una cita. Un llamado por paper no tiene de dónde citar el paso que no está.

### escala sin frase de porqué

- Subcaso del artefacto 3. Attention sí tiene la frase de los gradientes (citada arriba) y la palabra `variance` no aparece en el JSON: el porqué está, con otras palabras. Si en el paper no hay frase con `gradient` / `scale` / `counteract` / `variance` / `normal`, el dibujo lleva el pie fijo que ya existe («sin dividir, casi todo el peso cae en una sola clave») y no hay nota. **[V]** la frase de Attention. **[I]** no abrí el párrafo equivalente de Informer y de Layer Norm línea por línea; el dibujo no depende de eso.

### símbolo que no está en el párrafo de al lado

- Ya lo hace `gaps.py` (`missing`). En una pasada aparte, un subíndice de dos letras o un `\mathcal` ausente del párrafo vecino marcó 113 de 1436 ecuaciones en 16 papers, y entre los aciertos había `\mathrm{for}`. **[V]** la pasada; no está en el script para no pasar de 200 líneas. No ampliaría ese hueco: el falso positivo es el producto.

### número suelto

- Un decimal dentro del latex que no está en la prosa pega sobre todo en `\vspace{-0.1cm}` y en `[0.4ex]`. **[V]** leí esos aciertos (3104000, 3259798). No es un hueco. El `0.5` del logit de confianza y el `-0.5` de la tasa sí son constantes de la fórmula; la tasa está explicada en la frase siguiente («inverse square root», `warmup_steps=4000`) y el logit es la curva del tipo 5.

## Prueba con Muse

Dos llamados a `muse-spark-1.3` (estándar, no contributor). Tarifas de `rrm/reader/notes.py`: entrada $1.25 / millón, caché $0.15 / millón, salida $4.25 / millón. La API no devuelve dólares; el costo es tokens × esa tarifa. Caché 0 en los dos.

| llamado | entrada | salida | de ellos, razonamiento | costo USD | para qué |
| --- | --- | --- | --- | --- | --- |
| 1 | 803 | 800 | 770 | 0.00440375 | el JSON salió cortado; no usé el veredicto |
| 2 | 665 | 942 | 755 | 0.00483475 | 5 casos, veredictos abajo |
| **total** | | | | **0.00923850** | bajo el tope de $0.30 |

Veredictos del segundo llamado. **[V]** el JSON; **[I]** si le hago caso.

- Tasa de Attention: `dibujo_sin_nota`. De acuerdo: el párrafo explica la subida y la bajada, y la curva enseña el quiebre.
- Agenda de DANN (`\gamma=10`): `dibujo_sin_nota`. De acuerdo.
- Logit de confianza: `ya_explicado`. El párrafo dice los extremos y que es un logit. La curva seguiría mostrando el cruce en 0.5; no hace falta nota.
- NetVLAD, «it is easy to see that the term cancels»: `ya_explicado`. De acuerdo: la nota repetiría la oración.
- Softmax de NMT: `nota_de_cita`, «solo dice normalizar». No le hago caso: no hay otra frase en el paper que diga por qué softmax. Una nota sería texto de libro, no cita. El pie de código («suma 1 sobre k») basta.

Conclusión de la prueba: Muse, en estos cinco, o repite el párrafo o pide una nota sin fuente. No lo usaría para clasificar huecos. El razonamiento se come la salida (770 de 800 en el primer llamado): aunque se usara, hay que dejar `max_output_tokens` holgado o el JSON no llega.

## Ranking por beneficio neto

Beneficio neto = papers a los que les cambia la lectura, menos ruido, menos líneas. **[I]** el orden; **[V]** los conteos.

| lugar | tipo | papers | por qué ahí |
| --- | --- | --- | --- |
| 1 | forma | 13 | La duda más común y el widget más chico. Con tope de una pastilla por sección. |
| 2 | pasos | 11 | El algoritmo hoy es un párrafo. Partirlo no inventa nada. |
| 3 | escala | 4 | La duda más aguda, y el dibujo ya existe. Falta el detector y el caso Layer Norm. |
| 4 | casos | 8 | Lista de ramas. Poco código, poco ruido. |
| 5 | rejilla | 2 | Cabe en el mismo cambio que la escala. DCT deja de ser un caso especial de Attention. |
| 6 | curva | 4 | Sirve, y Muse coincidió en dos. El evaluador nuevo es el riesgo; va después. |
| 7 | supuesto (nota-cita) | 18 | La nota es la frase. Muchos papers, cero invención. |
| 8 | campo | 5 | Solo la caja de etiquetas. Sin integrar. |
| 9 | objetivo | 6 | Útil, parse frágil, un falso amigo (NetVLAD). |
| 10 | atajo | 6 | La figura del autor ya está. No redibujar. |
| — | barras opacas | 8 | Pie de una línea. Sin alturas inventadas. |
| — | salto como nota generada | 11 | La oración ya trae el resultado. |
| — | número suelto | — | Pega en `\vspace`. |

## Qué implementar antes del 4 nov, 8 pm CDMX

Un PR, sin Muse nuevo. Estimación **[I]**, suma ~710 líneas netas, bajo ~800.

| pieza | líneas | qué hace |
| --- | --- | --- |
| forma | 160 | detectar `\mathbb{R}^{...}` compuesta, una pastilla por sección, test del regex |
| pasos | 240 | recortar el entorno `algorithm`, stepper, no mostrar el párrafo de más |
| escala + rejilla | 140 | ampliar el detector; Layer Norm en dos columnas sin softmax; DCT por la misma heatmap |
| casos | 90 | partir `cases` / `array`+`if` en renglones |
| supuesto | 80 | la nota es la frase, sin llamado |
| **total** | **~710** | |

Fuera de ese PR: curva (evaluador), campo, objetivo, atajo, barras ilustrativas, salto generado.

Tres riesgos de ese PR:

1. Boyd llena la página de pastillas si el tope de una por sección no se prueba con 37925315.
2. El algoritmo de Informer viene dentro de un párrafo de apéndice: el corte tiene que ser el entorno, no la fila.
3. Layer Norm no es un softmax. Reusar `compareOf` tal cual dibuja la cosa equivocada.

## Qué no hice

- No implementé widgets. El script de conteo es `scripts/research/rrm57_tipos.py` (179 líneas, sin red).
- No bajé arXiv. Las 8 fuentes LaTeX del otro tar se usaron solo para contar figuras y entornos `algorithm` ya incluidos en los JSON.
- Modal: $0. Meta: $0.00923850, detalle en la tabla de arriba.
