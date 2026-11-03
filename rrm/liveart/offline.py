"""Selector, banco de dudas y verificador. Ninguno llama a un modelo.

El banco es la fase de emulación: las mismas dudas que el prompt le pide
a Muse, con una respuesta fija para poder calificar sin red. Si el enunciado
no merece widget, no hay preguntas ni explicación.
"""

import math
import re

from rrm.liveart.contract import LIMITS, RESERVED_IDS, banned_in, live_on, network_in
from rrm.liveart.fewshots import DRAWS
from rrm.reader.promptguard import injection

_FORCE = re.compile(
    r"merit must be|m[eé]rito debe ser|emit(?:e|ir)?\s+fetch|call fetch|<\s*script|javascript:|"
    r"disregard (?:all |any |the )?(?:above|previous)|new instructions\s*:",
    re.I,
)
_ABSURD = re.compile(
    r"\bpizza\b|margherita|\bperro\b|\bcat said\b|2\s*\+\s*2\s*=\s*5|\bunicorn\b",
    re.I,
)
_RESULT = re.compile(
    r"\bBLEU\b|\bSOTA\b|state of the art|state-of-the-art|\boutperforms?\b|"
    r"\d+(?:\.\d+)?\s*(?:×|x)\s+(?:smaller|deeper|larger|bigger|faster)|"
    r"\d+(?:\.\d+)?\s*%",
    re.I,
)
_MATH = re.compile(r"\$|\\(?:frac|sqrt|sum|sin|cos)|=")
_SLOP = re.compile(
    r"\b(?:confetti|sparkles?|rainbow)\b|"
    r"\bno need to explain\b|"
    r"\bpretty bouncing\b|"
    r"\bslider only changes the (?:color|hue|speed)\b|"
    r"\bjust animate\b",
    re.I,
)
_DECOR_IDS = frozenset({"hue", "color", "colour", "speed", "bounce", "sparkle", "party"})
_PAINT = re.compile(r"fillStyle|strokeStyle|globalAlpha")
_SEAL = re.compile(r"verified|from the paper|✓|✔", re.I)
_ID = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
_DRAW = re.compile(r"^function draw\s*\(")


def _both(blob, left, right):
    return 1 if left.search(blob) and right.search(blob) else 0


def _yarn(blob):
    score = 2 if re.search(r"\byarn\b|ntk-aware|ntk aware", blob, re.I) else 0
    if re.search(r"\bscale\b|\bescala\b", blob, re.I) and re.search(r"\brope\b|context", blob, re.I):
        score += 1
    return score


def _contrastive(blob):
    return _both(
        blob,
        re.compile(r"contrastive|simclr|infonce", re.I),
        re.compile(r"\btemperature\b|\btemperatura\b|\btau\b", re.I),
    )


def _attention(blob):
    return _both(
        blob,
        re.compile(r"\\sqrt|\bsqrt\b|ra[ií]z", re.I),
        re.compile(r"d_k|d_\{k\}|d_model|softmax|dot[- ]product", re.I),
    )


def _dpo(blob):
    if re.search(r"\bdpo\b|direct preference", blob, re.I):
        return 2
    if (
        re.search(r"\bpreference\b", blob, re.I)
        and re.search(r"\\beta|\bbeta\b", blob, re.I)
        and re.search(r"\bkl\b|policy|reward|reference", blob, re.I)
    ):
        return 1
    return 0


def _positional(blob):
    score = 0
    if re.search(r"positional encoding|encoding posicional", blob, re.I):
        score += 1
    if re.search(r"(?:\\sin|\bsin\s*\().{0,160}10000|10000.{0,160}(?:\\sin|\bsin\s*\()", blob, re.I | re.S):
        score += 1
    return score


def _softmax_temp(blob):
    if not re.search(r"softmax|logit", blob, re.I):
        return 0
    if re.search(r"\btemperature\b|\btemperatura\b|\\tau|\btau\b", blob, re.I):
        return 1
    return 0


def _stddev(blob):
    if re.search(r"standard deviation|desviaci[oó]n est[aá]ndar|layer\s*norm|layernorm", blob, re.I):
        return 1
    # (x-mu)/sigma y \frac{x}{\sigma}. Una barra sola no alcanza: hace falta sigma en el divisor.
    return 1 if re.search(r"/\s*(?:\\sigma|\bsigma\b)|\\frac\{[^{}]*\}\{\s*\\sigma\b", blob, re.I) else 0


def _rope(blob):
    score = 1 if re.search(r"\brope\b|rotary embedding|rotary position", blob, re.I) else 0
    if re.search(r"rotat\w{0,12}.{0,48}position|position.{0,48}rotat", blob, re.I):
        score += 1
    return score


def _speculative(blob):
    return 1 if re.search(r"speculative decoding|draft (?:model|token)|acceptance (?:rate|probability)", blob, re.I) else 0


def _noise(blob):
    if re.search(r"noise schedule|\\beta_t|\bbeta_t\b", blob, re.I):
        return 2
    return _both(blob, re.compile(r"diffusion", re.I), re.compile(r"timestep|\bbeta\b", re.I))


def _guidance(blob):
    return 1 if re.search(r"classifier-free guidance|guidance scale", blob, re.I) else 0


def _detr(blob):
    if re.search(r"bipartite matching|\bhungarian\b", blob, re.I):
        return 2
    return _both(blob, re.compile(r"matching", re.I), re.compile(r"object quer|set prediction", re.I))


def _residual(blob):
    return 1 if re.search(r"residual connection|skip connection|identity mapping|residual block", blob, re.I) else 0


def _nucleus(blob):
    return 1 if re.search(r"nucleus sampling|\btop-p\b|\btop_p\b", blob, re.I) else 0


def _rmsnorm(blob):
    return 2 if re.search(r"rmsnorm|rms\s*norm|root mean square", blob, re.I) else 0


def _swiglu(blob):
    return 2 if re.search(r"swiglu|swish\s*gate|silu\s*gate", blob, re.I) else 0


def _gqa(blob):
    return 2 if re.search(r"grouped-query|grouped query|\bgqa\b|n_kv_heads|kv heads", blob, re.I) else 0


def _multihead(blob):
    if re.search(r"multi-head|multihead|number of heads", blob, re.I):
        return 1
    if re.search(r"\bheads\b", blob, re.I) and re.search(r"d_model|attention", blob, re.I):
        return 1
    return 0


def _alibi(blob):
    return 2 if re.search(r"\balibi\b|attention with linear biases", blob, re.I) else 0


def _gelu(blob):
    return 1 if re.search(r"\bgelu\b", blob, re.I) else 0


def _smooth(blob):
    return 1 if re.search(r"label smoothing", blob, re.I) else 0


def _dropout(blob):
    return 1 if re.search(r"dropout rate|drop probability|p_drop", blob, re.I) else 0


def _warmup(blob):
    return 1 if re.search(r"learning rate warmup|warmup steps|linear warmup", blob, re.I) else 0


def _moe(blob):
    if re.search(r"mixture of experts|\bmoe\b", blob, re.I):
        return 2
    if re.search(r"\bexperts?\b", blob, re.I) and re.search(r"\brouter\b|top-k", blob, re.I):
        return 2
    return 0


def _topk(blob):
    if re.search(r"top-p|nucleus", blob, re.I):
        return 0
    return 1 if re.search(r"top-k sampling|\btop-k\b", blob, re.I) else 0


def _focal(blob):
    return 1 if re.search(r"focal loss", blob, re.I) else 0


def _giou(blob):
    return 2 if re.search(r"\bgiou\b|generalized intersection over union", blob, re.I) else 0


def _ppo(blob):
    if re.search(r"\bppo\b|proximal policy", blob, re.I):
        return 2
    return _both(
        blob,
        re.compile(r"probability ratio|surrogate objective", re.I),
        re.compile(r"\\epsilon|\bepsilon\b|\bclip(?:ped)?\b", re.I),
    )


def _nerf(blob):
    if re.search(r"\bnerf\b|neural radiance", blob, re.I):
        return 2
    return _both(blob, re.compile(r"frequenc", re.I), re.compile(r"radiance|view synthesis", re.I))


def _vit(blob):
    if re.search(r"vision transformer|\bvit\b", blob, re.I) and re.search(r"\bpatch", blob, re.I):
        return 2
    return 1 if re.search(r"patch size", blob, re.I) else 0


def _online_softmax(blob):
    if re.search(r"flashattention|online softmax|running max", blob, re.I):
        return 2
    return _both(blob, re.compile(r"softmax", re.I), re.compile(r"block by block|por bloques", re.I))


def _chinchilla(blob):
    if re.search(r"chinchilla", blob, re.I):
        return 2
    return _both(
        blob,
        re.compile(r"compute budget|6\s*ND|iso-flop", re.I),
        re.compile(r"model size|N\^0\.34|tokens", re.I),
    )


def _adam(blob):
    if re.search(r"\badam\b", blob, re.I):
        return 2
    return _both(blob, re.compile(r"first moment", re.I), re.compile(r"second moment", re.I))


def _spec_cost(blob):
    if not re.search(r"speculative decoding|draft (?:model|token|length)", blob, re.I):
        return 0
    if re.search(r"speedup|draft length|\bgamma\b", blob, re.I):
        return 2
    return 0


def _yarn_parts(blob):
    if re.search(r"ntk-by-parts|by-parts|by parts", blob, re.I):
        return 3
    return _both(
        blob,
        re.compile(r"\byarn\b|\brope\b", re.I),
        re.compile(r"wavelength|high-frequency|untouched", re.I),
    )


def _batchnorm(blob):
    return 2 if re.search(r"batch\s*norm", blob, re.I) else 0


def _distill(blob):
    if re.search(r"distill|dark knowledge", blob, re.I):
        return 2
    return _both(blob, re.compile(r"teacher", re.I), re.compile(r"temperature|softmax", re.I))


def _lora(blob):
    if re.search(r"\blora\b|low-rank adaptation", blob, re.I):
        return 2
    return _both(blob, re.compile(r"low-rank", re.I), re.compile(r"matri(?:x|ces)|update", re.I))


def _kl_rlhf(blob):
    if re.search(r"\bdpo\b|direct preference", blob, re.I):
        return 0
    return _both(
        blob,
        re.compile(r"\brlhf\b|reference policy", re.I),
        re.compile(r"\bbeta\b|reward", re.I),
    )


def _beam(blob):
    return 2 if re.search(r"beam search|beam width", blob, re.I) else 0


def _bpe(blob):
    if re.search(r"byte-pair|\bbpe\b", blob, re.I):
        return 2
    return 1 if re.search(r"most frequent adjacent pair", blob, re.I) else 0


def _smoothquant(blob):
    if re.search(r"smoothquant", blob, re.I):
        return 2
    return _both(blob, re.compile(r"outlier", re.I), re.compile(r"activation", re.I))


def _ssm(blob):
    if re.search(r"\bmamba\b|selective state space", blob, re.I):
        return 2
    return _both(blob, re.compile(r"\bdelta\b", re.I), re.compile(r"hidden state|resets", re.I))


# Orden = desempate. El más específico va primero.
TOPICS = (
    {
        "name": "online_softmax",
        "score": _online_softmax,
        "controls": ("blocks",),
        "mark": "bloque",
        "explain": (
            "El softmax se arma por bloques. Cada bloque trae su máximo y su suma, "
            "y la suma vieja se reescala si el máximo sube. En el último bloque las barras "
            "coinciden con el softmax de toda la lista."
        ),
        "questions": (
            ("¿El softmax por bloques es una aproximación?", "en el último bloque la diferencia con la lista completa es cero"),
            ("¿Por qué reescalar la suma cuando sube el máximo?", "los bloques viejos se contaron con otro máximo"),
            ("¿Qué se ahorra si no se guardan todos los puntajes?", "basta el máximo y la suma, no la matriz"),
        ),
    },
    {
        "name": "chinchilla",
        "score": _chinchilla,
        "controls": ("budget",),
        "mark": "valle",
        "explain": (
            "Con un cómputo fijo, agrandar el modelo obliga a ver menos datos. "
            "La pérdida hace un valle: hay un tamaño mejor, y el fondo se corre si el presupuesto crece."
        ),
        "questions": (
            ("¿Por qué no poner todo el cómputo en un modelo más grande?", "los datos se achican y la pérdida vuelve a subir"),
            ("¿Qué se mueve cuando sube el presupuesto?", "el fondo del valle se corre hacia un modelo mayor"),
            ("¿Qué se está eligiendo, el tamaño o los tokens?", "los dos, sobre la curva de cómputo fijo"),
        ),
    },
    {
        "name": "adam",
        "score": _adam,
        "controls": ("lr",),
        "mark": "momento",
        "explain": (
            "Adam divide el paso entre la raíz del segundo momento, así que una dirección ruidosa se achica. "
            "En un valle angosto, SGD rebota en la pared y Adam baja por el centro."
        ),
        "questions": (
            ("¿Por qué SGD zigzaguea y Adam no, con el mismo paso?", "Adam achica la dirección que más varía"),
            ("¿Qué pasa si el paso es demasiado grande?", "SGD se sale del valle y Adam aguanta más"),
            ("¿Qué se está normalizando, el gradiente o los datos?", "el paso se divide entre la raíz del segundo momento"),
        ),
    },
    {
        "name": "spec_cost",
        "score": _spec_cost,
        "controls": ("agree", "cost"),
        "mark": "largo",
        "explain": (
            "Alargar el borrador solo conviene mientras lo aceptan. Cada token de más cuesta una fracción "
            "del modelo grande, así que el ahorro sube y después cae: hay un largo mejor."
        ),
        "questions": (
            ("¿Por qué no dejar que el borrador proponga cincuenta tokens?", "los rechazados se pagan y el ahorro cae"),
            ("¿Qué mueve el largo mejor, el acuerdo o el costo?", "los dos: si el acuerdo baja, el mejor se acorta"),
            ("¿Cuándo el borrador sale más lento que generar directo?", "cuando la cola de la curva baja de uno"),
        ),
    },
    {
        "name": "yarn_parts",
        "score": _yarn_parts,
        "controls": ("scale",),
        "mark": "lenta",
        "explain": (
            "YaRN no estira todas las frecuencias. Las rápidas ya dan varias vueltas dentro del contexto y se quedan. "
            "Las lentas, cuya onda es más larga que el contexto, sí se interpolan."
        ),
        "questions": (
            ("¿Por qué no dividir todas las posiciones entre la escala?", "las frecuencias altas ya cabían y estirarlas las deforma"),
            ("¿Qué dimensión se toca cuando el contexto crece?", "la que todavía no dio una vuelta dentro del contexto"),
            ("¿Qué queda igual en las frecuencias altas?", "su ángulo no se divide"),
        ),
    },
    {
        "name": "batchnorm",
        "score": _batchnorm,
        "controls": ("scale",),
        "mark": "lote",
        "explain": (
            "BatchNorm resta la media del lote y divide entre su desviación. "
            "La fila de adelante deja de ver la escala de la entrada; gamma y beta la vuelven a estirar después."
        ),
        "questions": (
            ("¿Por qué la capa siguiente no ve la escala de la entrada?", "el lote ya quedó en media cero y ancho uno"),
            ("¿Qué vuelve a estirar la fila de abajo?", "gamma y beta, después de normalizar"),
            ("¿Qué se está centrando, un dato o el lote?", "la media y la desviación son del lote"),
        ),
    },
    {
        "name": "distill_temp",
        "score": _distill,
        "controls": ("temp",),
        "mark": "maestro",
        "explain": (
            "Subir la temperatura del maestro saca las probabilidades chicas, las que el argmax esconde. "
            "El alumno aprende de ese orden, no solo de la clase ganadora."
        ),
        "questions": (
            ("¿Por qué entrenar con las probabilidades del maestro?", "el orden entre las clases perdedoras también informa"),
            ("¿Qué aparece cuando sube la temperatura?", "las probabilidades chicas se vuelven legibles"),
            ("¿Qué se aplasta si la temperatura vuelve a uno?", "otra vez solo se ve la clase ganadora"),
        ),
    },
    {
        "name": "lora",
        "score": _lora,
        "controls": ("rank",),
        "mark": "rango",
        "explain": (
            "LoRA escribe el cambio de peso como el producto de dos matrices flacas. "
            "Subir el rango suma un patrón, y los parámetros crecen como 2 por d por rango, no como d al cuadrado."
        ),
        "questions": (
            ("¿Cómo un rango chico cambia una matriz enorme?", "cada rango suma un patrón de rango uno"),
            ("¿Qué crece más rápido, el rango o el costo?", "el costo es lineal en el rango, cuadrático si se entrena todo"),
            ("¿Qué se está entrenando, la matriz completa o el factor?", "solo las dos matrices flacas"),
        ),
    },
    {
        "name": "kl_rlhf",
        "score": _kl_rlhf,
        "controls": ("beta",),
        "mark": "referencia",
        "explain": (
            "La política óptima mezcla el premio con la referencia: crece como exp(premio / beta) sobre la referencia. "
            "Beta chico, y el token premiado se queda con toda la masa."
        ),
        "questions": (
            ("¿Por qué no elegir siempre el token de más premio?", "beta chico sí lo hace; beta grande lo frena la referencia"),
            ("¿Qué crece cuando beta baja?", "la distancia a la política de referencia"),
            ("¿Qué frena beta, el premio o la referencia?", "qué tanto se puede alejar de la referencia"),
        ),
    },
    {
        "name": "beam",
        "score": _beam,
        "controls": ("width",),
        "mark": "ancho",
        "explain": (
            "El haz guarda las continuaciones mejores hasta ahora. "
            "Ancho uno es el codicioso y puede perder: un primer token peor a veces termina en una frase mejor."
        ),
        "questions": (
            ("¿Por qué no elegir siempre la palabra más probable?", "un arranque peor puede terminar mejor"),
            ("¿Qué cambia cuando el ancho pasa de uno a dos?", "entra la rama que el codicioso había tirado"),
            ("¿Qué se está guardando, la frase final o el camino?", "el haz guarda los mejores caminos a medio hacer"),
        ),
    },
    {
        "name": "bpe_merge",
        "score": _bpe,
        "controls": ("merges",),
        "mark": "par",
        "explain": (
            "BPE pega, una y otra vez, el par de símbolos que más se repite. "
            "Las palabras frecuentes se vuelven un token; una palabra nueva se parte con esas fusiones."
        ),
        "questions": (
            ("¿Por qué fusionar el par más frecuente y no la palabra entera?", "el par sirve en varias palabras"),
            ("¿Cómo se parte una palabra que no estaba en el vocabulario?", "con las fusiones ya hechas, de a caracteres"),
            ("¿Qué se ve al avanzar el número de fusiones?", "los cuadros vecinos se juntan en uno"),
        ),
    },
    {
        "name": "smoothquant",
        "score": _smoothquant,
        "controls": ("alpha",),
        "mark": "outlier",
        "explain": (
            "SmoothQuant pasa el outlier de la activación al peso, con una escala alpha. "
            "El error tiene un valle: alpha de más lo deja en el peso, alpha de menos lo deja en la activación."
        ),
        "questions": (
            ("¿Por qué no cuantizar la activación tal cual?", "un outlier se come el rango y el resto se aplasta"),
            ("¿Qué pasa si alpha se va a un extremo?", "el error sube; el fondo está entre los dos"),
            ("¿Quién se queda con el outlier?", "alpha lo reparte entre la activación y el peso"),
        ),
    },
    {
        "name": "ssm_delta",
        "score": _ssm,
        "controls": ("delta",),
        "mark": "paso",
        "explain": (
            "En el modelo selectivo, delta es el tamaño del paso. Grande, y el estado se olvida y se queda con la entrada de ahora. "
            "Chico, y el estado sigue y la entrada casi no entra."
        ),
        "questions": (
            ("¿Qué hace un delta grande con la memoria?", "la borra y la reemplaza con la entrada actual"),
            ("¿Qué se ignora cuando delta es chico?", "la entrada de este token"),
            ("¿Por qué no alcanza con una compuerta fija?", "delta cambia con el token: a veces recuerda y a veces resetea"),
        ),
    },
    {
        "name": "giou",
        "score": _giou,
        "controls": ("gap",),
        "mark": "encierre",
        "explain": (
            "IoU vale cero en cuanto las cajas no se tocan. GIoU resta lo que queda vacío dentro del encierre mínimo, "
            "así que alejarlas sigue bajando el puntaje."
        ),
        "questions": (
            ("¿Por qué dos cajas que no se tocan tienen el mismo IoU?", "en cuanto no hay intersección el IoU vale cero"),
            ("¿Qué resta GIoU cuando las cajas se separan?", "la fracción vacía del encierre mínimo"),
            ("¿Qué crece si las alejo: el IoU o el hueco del encierre?", "el IoU se queda y el encierre se vacía"),
        ),
    },
    {
        "name": "ppo_clip",
        "score": _ppo,
        "controls": ("eps", "ratio"),
        "mark": "recorte",
        "explain": (
            "El recorte de PPO aplana el objetivo cuando el ratio sale de la banda 1±épsilon. "
            "Con advantage positivo se aplana a la derecha; con negativo, a la izquierda."
        ),
        "questions": (
            ("¿Por qué el objetivo deja de subir si el ratio pasa de 1+épsilon?", "el recorte no paga un ratio más grande"),
            ("¿Qué lado se aplana cuando el advantage es negativo?", "se aplana por debajo de 1−épsilon"),
            ("¿Qué se recorta: el ratio o la recompensa del entorno?", "se recorta el ratio dentro del objetivo"),
        ),
    },
    {
        "name": "nerf_freq",
        "score": _nerf,
        "controls": ("levels",),
        "mark": "frecuencia",
        "explain": (
            "NeRF suma frecuencias dobles sobre la coordenada. Con un nivel el borde queda ancho; "
            "con más niveles el mismo borde se vuelve un pico."
        ),
        "questions": (
            ("¿Por qué un solo nivel no puede dibujar un borde fino?", "una frecuencia baja es una onda ancha"),
            ("¿Qué le pasa al pico si subo los niveles?", "se angosta alrededor de la coordenada"),
            ("¿Qué estoy subiendo: la cámara o la frecuencia máxima?", "el control es el número de frecuencias"),
        ),
    },
    {
        "name": "vit_patch",
        "score": _vit,
        "controls": ("patch",),
        "mark": "parche",
        "explain": (
            "El parche es el token. Si crece, la imagen se parte en menos piezas y cada pieza promedia más píxeles, "
            "así que el detalle se pierde."
        ),
        "questions": (
            ("¿Por qué un parche grande ya no muestra la forma?", "cada token promedia un bloque más grande"),
            ("¿Qué es un token aquí: un píxel o un parche?", "el modelo ve parches, no píxeles sueltos"),
            ("¿Qué pasa con el número de tokens si el parche se achica?", "entran más piezas y vuelve el detalle"),
        ),
    },
    {
        "name": "yarn_scale",
        "score": _yarn,
        "controls": ("scale",),
        "mark": "escala",
        "explain": (
            "YaRN cambia la escala de las frecuencias de RoPE para un contexto más largo que el de entrenamiento. "
            "Al estirar la escala, las vueltas que cubrían el entrenamiento ahora cubren más tokens."
        ),
        "questions": (
            ("¿Por qué hay que reescalar RoPE si el contexto crece?", "sin escala el ángulo se sale de lo entrenado"),
            ("¿Qué se deforma en las frecuencias altas al estirar la escala?", "las vueltas rápidas se comprimen"),
            ("¿Qué se alarga: el texto o las vueltas del ángulo?", "el control mueve la escala, no el texto"),
        ),
    },
    {
        "name": "contrastive_temp",
        "score": _contrastive,
        "controls": ("tau",),
        "mark": "temperatura",
        "explain": (
            "En el contraste, la temperatura parte las similitudes antes del softmax. "
            "Baja, y el positivo se queda con el lote; alta, y positivos y negativos se parecen."
        ),
        "questions": (
            ("¿Por qué una temperatura baja aplasta el lote en el positivo?", "el softmax se vuelve casi seguro"),
            ("¿Qué se confunde si la temperatura es muy alta?", "positivos y negativos pesan parecido"),
            ("¿Qué se está escalando: las similitudes o las etiquetas?", "solo las similitudes entran al softmax"),
        ),
    },
    {
        "name": "attention_scale",
        "score": _attention,
        "controls": ("d",),
        "mark": "raíz",
        "explain": (
            "El producto QK crece con la dimensión. Dividir entre la raíz de d_k deja el softmax "
            "en una zona donde más de una clave todavía pesa."
        ),
        "questions": (
            ("¿Por qué se divide entre la raíz de d_k y no entre d_k?", "la varianza del producto es d_k, no d_k al cuadrado"),
            ("¿Qué le pasa al softmax si el producto crece con la dimensión?", "una sola clave se queda con el peso"),
            ("¿Cómo se reparte el peso de una clave con y sin esa división?", "el dibujo muestra las dos filas"),
        ),
    },
    {
        "name": "dpo_beta",
        "score": _dpo,
        "controls": ("beta",),
        "mark": "beta",
        "explain": (
            "Beta dice cuánto puede alejarse la política nueva de la de referencia. "
            "Chico, y el modelo persigue el premio aunque se desvíe; grande, y se queda cerca."
        ),
        "questions": (
            ("¿Por qué un beta chico deja que la política se aleje más?", "el freno contra la referencia pesa menos"),
            ("¿Qué se está frenando: el premio o la distancia a la referencia?", "beta pesa esa distancia"),
            ("¿Cómo se ve el premio implícito si subo beta?", "el log-ratio se encoge"),
        ),
    },
    {
        "name": "positional_encoding",
        "score": _positional,
        "controls": ("base", "dim"),
        "mark": "base",
        "explain": (
            "Cada par de dimensiones es una onda. La base cambia qué tan rápido gira: "
            "las primeras vuelven seguido y las últimas casi no. Por eso una posición cercana se parece y una lejana no."
        ),
        "questions": (
            ("¿Por qué una base más grande hace más lentas las dimensiones altas?", "la base está en el exponente de la frecuencia"),
            ("¿Qué se confunde si todas las ondas van igual de rápido?", "la posición deja de separarse entre dimensiones"),
            ("¿Cómo cabe una frase larga en un seno y un coseno?", "las frecuencias bajas dan vueltas despacio"),
            ("¿Por qué una posición cercana se parece y una lejana no?", "el producto de las ondas cae con la distancia"),
        ),
    },
    {
        "name": "softmax_temperature",
        "score": _softmax_temp,
        "controls": ("temp",),
        "mark": "temperatura",
        "explain": (
            "La temperatura parte los logits antes del softmax. "
            "Baja, y casi toda la masa cae en la opción más alta; alta, y las opciones se parecen."
        ),
        "questions": (
            ("¿Por qué bajar la temperatura vuelve una sola opción casi segura?", "el softmax se concentra en el logit mayor"),
            ("¿Qué queda de la distribución si la temperatura es muy alta?", "las opciones se acercan"),
            ("¿Qué se está moviendo: los logits o las palabras?", "el control parte los logits"),
        ),
    },
    {
        "name": "stddev",
        "score": _stddev,
        "controls": ("sigma",),
        "mark": "desviación",
        "explain": (
            "La desviación estándar es el ancho de la nube alrededor de la media. "
            "Al dividir entre sigma, puntos lejanos y cercanos quedan en la misma escala."
        ),
        "questions": (
            ("¿Qué cambia en los puntos si subo la desviación estándar?", "la nube se abre alrededor de la media"),
            ("¿Por qué dividir entre sigma los pone en la misma escala?", "se quita el ancho de la nube"),
            ("¿Qué tan lejos de la media queda un punto cuando sigma es chico?", "la misma distancia numérica pesa más"),
        ),
    },
    {
        "name": "rope",
        "score": _rope,
        "controls": ("theta",),
        "mark": "gira",
        "explain": (
            "RoPE gira cada token según su posición. Si ambos se corren igual, "
            "el ángulo entre ellos no cambia y el parecido queda. Separarlos sí abre el ángulo."
        ),
        "questions": (
            ("¿Por qué correr los dos tokens no cambia el parecido?", "ambos giran el mismo extra y el ángulo entre ellos queda"),
            ("¿Qué pasa con el ángulo si los tokens quedan más lejos?", "la diferencia de giros crece"),
            ("¿En qué se distingue esto de sumar un seno al embedding?", "aquí la posición es una rotación"),
        ),
    },
    {
        "name": "speculative",
        "score": _speculative,
        "controls": ("agree",),
        "mark": "borrador",
        "explain": (
            "El modelo chico propone un borrador y el grande lo acepta token por token. "
            "Si se parecen, la racha aceptada crece y se ahorran pasos del modelo grande."
        ),
        "questions": (
            ("¿Por qué un borrador parecido alarga la racha aceptada?", "el grande confirma varios tokens de un jalón"),
            ("¿Qué se paga cuando el modelo grande rechaza un token?", "se tira el resto del borrador"),
            ("¿Dónde se gana tiempo: en proponer o en verificar?", "verificar un bloque sale más barato que generarlos"),
        ),
    },
    {
        "name": "noise_schedule",
        "score": _noise,
        "controls": ("beta",),
        "mark": "ruido",
        "explain": (
            "Cada paso del proceso directo suma ruido según beta_t. "
            "Si beta crece rápido, la imagen se pierde en pocos pasos; si crece lento, la señal aguanta más."
        ),
        "questions": (
            ("¿Por qué un beta_t grande borra la imagen más pronto?", "cada paso mete más ruido"),
            ("¿Qué queda de la señal a la mitad del horario de ruido?", "depende de qué tan rápido creció beta"),
            ("¿Qué se está moviendo: el paso o la cantidad de ruido?", "el control es la cantidad de ruido del paso"),
        ),
    },
    {
        "name": "guidance",
        "score": _guidance,
        "controls": ("scale",),
        "mark": "guía",
        "explain": (
            "La guía sin clasificador empuja la muestra hacia el texto restando la predicción sin condición. "
            "Sube la escala y el texto manda más; bájala y la imagen se parece al modelo sin prompt."
        ),
        "questions": (
            ("¿Por qué subir la escala pega más la imagen al texto?", "se amplifica la diferencia contra el modelo sin prompt"),
            ("¿Qué se pierde cuando la guía es demasiado alta?", "la muestra se sale de lo que el modelo sabe pintar"),
            ("¿Qué se está restando: la predicción con texto o la que va sin él?", "a la condicionada se le resta la otra"),
        ),
    },
    {
        "name": "detr_match",
        "score": _detr,
        "controls": ("class_w",),
        "mark": "emparej",
        "explain": (
            "Cada query se empareja con una sola caja. El costo mezcla clase y caja; "
            "si sube el peso de la clase, el emparejamiento prefiere la etiqueta aunque la caja quede peor."
        ),
        "questions": (
            ("¿Por qué cada query termina con una sola caja?", "el emparejamiento es uno a uno"),
            ("¿Qué cambia en el emparejamiento si pesa más la clase que la caja?", "gana la etiqueta aunque la caja se desplace"),
            ("¿Qué es el costo: la etiqueta, la posición, o las dos?", "el control mezcla las dos"),
        ),
    },
    {
        "name": "residual",
        "score": _residual,
        "controls": ("skip",),
        "mark": "atajo",
        "explain": (
            "El atajo suma la entrada del bloque con lo que el bloque calculó. "
            "Si se apaga, la señal tiene que cruzar la capa entera y se aplana más fácil."
        ),
        "questions": (
            ("¿Por qué sumar la entrada evita que la señal se aplaste?", "una parte cruza el bloque sin transformarse"),
            ("¿Qué le pasa al gradiente si quito el atajo?", "tiene que atravesar todas las capas"),
            ("¿Qué se está viendo: la entrada, la salida del bloque, o la suma?", "el control mezcla entrada y salida"),
        ),
    },
    {
        "name": "nucleus",
        "score": _nucleus,
        "controls": ("p",),
        "mark": "masa",
        "explain": (
            "Top-p se queda con el conjunto más chico de tokens cuya masa pasa de p. "
            "Bajas p y el conjunto se encoge a lo más seguro; lo subes y entran palabras más raras."
        ),
        "questions": (
            ("¿Por qué bajar p deja menos palabras posibles?", "la masa acumulada se llena antes"),
            ("¿En qué se distingue esto de cortar a un número fijo de opciones?", "el tamaño del conjunto depende de la masa"),
            ("¿Qué se está moviendo: la masa acumulada o el orden de los logits?", "p corta la masa, el orden no cambia"),
        ),
    },
    {
        "name": "rmsnorm",
        "score": _rmsnorm,
        "controls": ("eps",),
        "mark": "rms",
        "explain": (
            "RMSNorm divide cada coordenada entre la raíz del promedio de cuadrados, más un epsilon. "
            "Si subes el epsilon, la norma deja de achicar tanto los valores grandes."
        ),
        "questions": (
            ("¿Por qué RMSNorm no resta la media antes de dividir?", "solo usa el tamaño, no el centro"),
            ("¿Qué cambia en el vector si subo el epsilon?", "el divisor crece y los valores se encogen menos"),
            ("¿En qué se distingue esto de dividir entre la desviación estándar?", "aquí no se resta la media"),
        ),
    },
    {
        "name": "swiglu",
        "score": _swiglu,
        "controls": ("beta",),
        "mark": "compuerta",
        "explain": (
            "SwiGLU multiplica el camino lineal por una compuerta Swish. "
            "Si la compuerta se cierra, esa parte del vector se apaga."
        ),
        "questions": (
            ("¿Por qué la compuerta puede apagar una coordenada?", "el Swish puede valer casi cero"),
            ("¿Qué pasa con el vector si la compuerta se abre del todo?", "pasa el camino lineal casi entero"),
            ("¿Qué se multiplica: el Swish o el camino lineal?", "la compuerta multiplica al otro camino"),
        ),
    },
    {
        "name": "gqa",
        "score": _gqa,
        "controls": ("kv",),
        "mark": "grupo",
        "explain": (
            "En la atención por grupos, varias consultas comparten la misma llave. "
            "Si bajas los grupos, más consultas leen la misma memoria."
        ),
        "questions": (
            ("¿Por qué varias consultas comparten una sola llave?", "así la memoria de llaves no crece con las consultas"),
            ("¿Qué memoria se ahorra si bajo el número de grupos?", "se guardan menos llaves y valores"),
            ("¿Qué se está compartiendo: las consultas o las llaves?", "las consultas siguen aparte; se comparte la llave"),
        ),
    },
    {
        "name": "multihead",
        "score": _multihead,
        "controls": ("heads",),
        "mark": "cabezas",
        "explain": (
            "Multi-head parte el vector en cabezas. "
            "Más cabezas, y cada una ve un trozo más corto del mismo vector."
        ),
        "questions": (
            ("¿Por qué partir el vector en varias cabezas?", "cada una puede mirar otro patrón"),
            ("¿Qué le pasa a cada cabeza si subo h y el vector no cambia?", "el trozo de cada cabeza se acorta"),
            ("¿Qué se divide: el vector o el número de capas?", "se divide el vector, no la profundidad"),
        ),
    },
    {
        "name": "alibi",
        "score": _alibi,
        "controls": ("slope",),
        "mark": "pendiente",
        "explain": (
            "ALiBi resta una pendiente por la distancia entre tokens. "
            "Pendiente grande, y lo lejano pesa casi nada."
        ),
        "questions": (
            ("¿Por qué una pendiente castiga a los tokens lejanos?", "el castigo crece con la distancia"),
            ("¿Qué pasa con la atención si la pendiente es casi cero?", "cerca y lejos pesan parecido"),
            ("¿Qué se resta: la distancia o el producto de las consultas?", "se resta una pendiente por la distancia"),
        ),
    },
    {
        "name": "gelu",
        "score": _gelu,
        "controls": ("mix",),
        "mark": "gelu",
        "explain": (
            "GELU no corta en cero: deja pasar un poco los negativos. "
            "El control mezcla el corte seco y GELU para ver esa cola."
        ),
        "questions": (
            ("¿Por qué GELU deja pasar un poco los números negativos?", "el peso crece suave, no de golpe"),
            ("¿En qué se ve distinto de cortar en cero?", "a la izquierda del cero todavía hay cola"),
            ("¿Qué estoy mezclando: el corte seco o la cola suave?", "el control va de uno al otro"),
        ),
    },
    {
        "name": "label_smoothing",
        "score": _smooth,
        "controls": ("eps",),
        "mark": "suavizado",
        "explain": (
            "El suavizado de etiquetas reparte un poco de masa fuera de la clase correcta. "
            "Más epsilon, y la etiqueta queda más chata."
        ),
        "questions": (
            ("¿Por qué repartir masa fuera de la clase correcta?", "el modelo no se pone tan seguro de una sola clase"),
            ("¿Qué tan chata queda la etiqueta si epsilon es grande?", "la clase correcta baja y las otras suben"),
            ("¿Qué se mueve: la clase verdadera o las demás?", "las dos: una cede masa y las otras la reciben"),
        ),
    },
    {
        "name": "dropout",
        "score": _dropout,
        "controls": ("p",),
        "mark": "dropout",
        "explain": (
            "La tasa de dropout apaga más unidades de la máscara. "
            "Sube la tasa y el vector se queda con menos posiciones vivas."
        ),
        "questions": (
            ("¿Por qué apagar unidades durante el entrenamiento?", "el modelo no se apoya en una sola posición"),
            ("¿Qué le pasa al vector si la tasa de dropout sube?", "quedan menos unidades encendidas"),
            ("¿Qué estoy viendo: las unidades vivas o las apagadas?", "las apagadas son las que la tasa cruza"),
        ),
    },
    {
        "name": "warmup",
        "score": _warmup,
        "controls": ("steps",),
        "mark": "calentamiento",
        "explain": (
            "El calentamiento sube el paso de aprendizaje desde cero hasta el valor de trabajo. "
            "Si alargas esos pasos, a la mitad del camino el paso sigue chico."
        ),
        "questions": (
            ("¿Por qué el paso de aprendizaje empieza en cero?", "un paso grande al inicio mueve los pesos de más"),
            ("¿Qué pasa a mitad del camino si alargo el calentamiento?", "el paso todavía no llegó al valor de trabajo"),
            ("¿Qué sube: el paso o el número de capas?", "sube el paso, la red no cambia de profundidad"),
        ),
    },
    {
        "name": "moe",
        "score": _moe,
        "controls": ("k",),
        "mark": "expertos",
        "explain": (
            "El router manda cada token a unos pocos expertos. "
            "Si subes k, más expertos se prenden para el mismo token."
        ),
        "questions": (
            ("¿Por qué un token no usa todos los expertos?", "el costo sería el de activar la red entera"),
            ("¿Qué cambia si k pasa de uno a cuatro?", "el token mezcla más expertos"),
            ("¿Qué elige el router: el experto o el token?", "elige qué expertos atienden a ese token"),
        ),
    },
    {
        "name": "topk",
        "score": _topk,
        "controls": ("k",),
        "mark": "tope",
        "explain": (
            "Top-k deja solo el tope de k tokens y tira el resto. "
            "K chico, y una o dos palabras se quedan con toda la masa."
        ),
        "questions": (
            ("¿Por qué tirar todos los tokens fuera del tope?", "la masa se reparte solo entre los que quedan"),
            ("¿En qué se distingue un k chico de quedarse con casi todos?", "el conjunto permitido cambia de tamaño"),
            ("¿Qué se corta: la masa acumulada o el número de opciones?", "se corta el número, no un umbral de masa"),
        ),
    },
    {
        "name": "focal",
        "score": _focal,
        "controls": ("gamma",),
        "mark": "gamma",
        "explain": (
            "Focal loss baja el peso de lo que ya está bien clasificado, con gamma. "
            "Gamma grande, y los ejemplos fáciles casi no empujan."
        ),
        "questions": (
            ("¿Por qué bajar el peso de lo que ya está bien?", "si no, los fáciles dominan el gradiente"),
            ("¿Qué le pasa a un ejemplo fácil si gamma crece?", "su peso se acerca a cero"),
            ("¿Qué se está apagando: el error chico o el error grande?", "se apaga el error chico"),
        ),
    },
)


def _by_name(name):
    for topic in TOPICS:
        if topic["name"] == name:
            return topic
    return None


def _blob(claim):
    if isinstance(claim, str):
        return claim
    claim = claim or {}
    return "\n".join(str(claim.get(key) or "") for key in ("text", "latex", "context"))


def _decision(merit, topic, reason):
    return {"merit": merit, "topic": topic, "reason": reason}


def select_claim(claim):
    """widget si hay un parámetro que se puede mover. static si hay matemática sin tema. skip si no."""
    blob = _blob(claim)
    if injection(blob) or _FORCE.search(blob):
        return _decision("skip", "", "injection")
    if _ABSURD.search(blob):
        return _decision("skip", "", "absurd")
    if _SLOP.search(blob):
        return _decision("skip", "", "slop")
    scored = [(topic["score"](blob), topic) for topic in TOPICS]
    scored = [item for item in scored if item[0] > 0]
    if scored:
        scored.sort(key=lambda item: (-item[0], TOPICS.index(item[1])))
        return _decision("widget", scored[0][1]["name"], "mechanism")
    if _RESULT.search(blob):
        return _decision("skip", "", "result")
    if _MATH.search(blob):
        return _decision("static", "", "no_topic_math")
    return _decision("skip", "", "no_parameter")


def path_for(claim):
    """Sin la bandera no hay camino vivo: se queda el artefacto estático de hoy."""
    if not live_on():
        return "static"
    merit = select_claim(claim)["merit"]
    return "live" if merit == "widget" else merit


def _pack(claim, reason_ok):
    decision = select_claim(claim)
    if decision["merit"] != "widget":
        return decision, None
    return decision, _by_name(decision["topic"])


def questions_for(claim):
    decision, spec = _pack(claim, "bank")
    if spec is None:
        return {"questions": [], "reason": decision["reason"], "topic": ""}
    return {
        "questions": [{"q": q, "why": why} for q, why in spec["questions"]],
        "reason": "bank",
        "topic": spec["name"],
    }


def explain_for(claim):
    decision, spec = _pack(claim, "bank")
    if spec is None:
        return {"explain": "", "reason": decision["reason"], "topic": ""}
    return {"explain": spec["explain"], "reason": "bank", "topic": spec["name"]}


def gold_widget(topic):
    spec = _by_name(topic)
    raw = DRAWS.get(topic)
    if spec is None or raw is None:
        return None
    return {
        "id": topic.replace("_", "-"),
        "topic": topic,
        "title": raw["title"],
        "explain": spec["explain"],
        "questions": [{"q": q, "why": why} for q, why in spec["questions"]],
        "controls": [dict(item) for item in raw["controls"]],
        "draw": raw["draw"],
    }


def emulated_widget(claim):
    """El de oro si existe; si no, el primer emulado de ese tema. None si el enunciado no es widget."""
    decision = select_claim(claim)
    if decision["merit"] != "widget":
        return None
    gold = gold_widget(decision["topic"])
    if gold is not None:
        return gold
    from rrm.liveart.emulated import CATALOG

    for row in CATALOG:
        if row["widget"]["topic"] == decision["topic"]:
            return row["widget"]
    from rrm.liveart.guests import GUESTS

    for widget in GUESTS:
        if widget["topic"] == decision["topic"]:
            return widget
    return None


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def shape_errors(widget):
    if not isinstance(widget, dict):
        return ["not_object"]
    errors = []
    extra = set(widget) - {"id", "topic", "title", "explain", "questions", "controls", "draw"}
    if extra:
        errors.append("extra_keys")
    if widget.get("topic") not in {topic["name"] for topic in TOPICS}:
        errors.append("topic")
    title = widget.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > LIMITS["title"]:
        errors.append("title")
    explain = widget.get("explain")
    if not isinstance(explain, str) or not explain.strip() or len(explain) > LIMITS["explain"]:
        errors.append("explain")
    draw = widget.get("draw")
    if not isinstance(draw, str) or not _DRAW.match(draw.strip()) or len(draw) > LIMITS["draw"]:
        errors.append("draw")
    ident = widget.get("id")
    if ident is not None and (not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9-]{1,40}", ident)):
        errors.append("id")
    questions = widget.get("questions")
    if not isinstance(questions, list) or not LIMITS["questions_min"] <= len(questions) <= LIMITS["questions_max"]:
        errors.append("questions")
    else:
        for item in questions:
            if not isinstance(item, dict) or set(item) - {"q", "why"}:
                errors.append("question")
                break
            q, why = item.get("q"), item.get("why")
            if not isinstance(q, str) or not (12 <= len(q) <= LIMITS["question"]) or not q.endswith("?"):
                errors.append("question")
                break
            if not isinstance(why, str) or not why.strip() or len(why) > LIMITS["why"]:
                errors.append("question")
                break
    controls = widget.get("controls")
    if not isinstance(controls, list) or not LIMITS["controls_min"] <= len(controls) <= LIMITS["controls_max"]:
        errors.append("controls")
    else:
        seen = set()
        for item in controls:
            if not isinstance(item, dict) or set(item) != {"id", "label", "min", "max", "value", "step"}:
                errors.append("control")
                break
            kid, label = item.get("id"), item.get("label")
            if not isinstance(kid, str) or not _ID.match(kid) or kid in RESERVED_IDS or kid in seen:
                errors.append("control")
                break
            seen.add(kid)
            if not isinstance(label, str) or not label.strip() or len(label) > LIMITS["label"]:
                errors.append("control")
                break
            lo, hi, value, step = item.get("min"), item.get("max"), item.get("value"), item.get("step")
            if not all(_num(part) for part in (lo, hi, value, step)) or not lo < hi or step <= 0 or not lo <= value <= hi:
                errors.append("control")
                break
    return errors


def _on_claim(decision, widget):
    if decision["merit"] != "widget" or not isinstance(widget, dict):
        return False
    if widget.get("topic") != decision["topic"]:
        return False
    spec = _by_name(decision["topic"])
    if spec is None:
        return False
    ids = {item.get("id") for item in widget.get("controls") or [] if isinstance(item, dict)}
    if not ids & set(spec["controls"]):
        return False
    return spec["mark"] in str(widget.get("explain") or "").casefold()


def _payload(text):
    return bool(text) and (injection(text) or bool(_FORCE.search(text)))


def _echo(widget):
    """La orden copiada al título, la explicación o el draw también se rechaza."""
    if not isinstance(widget, dict):
        return False
    parts = [widget.get("title"), widget.get("explain"), widget.get("draw")]
    for item in widget.get("questions") or []:
        if isinstance(item, dict):
            parts.extend((item.get("q"), item.get("why")))
    return any(_payload(part) for part in parts if isinstance(part, str))


def _reads_control(draw, kid):
    return bool(re.search(r"state\." + re.escape(kid) + r"\b", draw)) or bool(
        re.search(r"state\[\s*['\"]" + re.escape(kid) + r"['\"]\s*\]", draw)
    )


def _line_at(draw, index):
    start = draw.rfind("\n", 0, index) + 1
    end = draw.find("\n", index)
    if end < 0:
        end = len(draw)
    return draw[start:end]


def _paint_only(draw, kid):
    reads = list(re.finditer(r"state\." + re.escape(kid) + r"\b", draw))
    if not reads:
        return False
    return all(_PAINT.search(_line_at(draw, match.start())) for match in reads)


def _slop_draw(widget):
    """El slider no mueve el parámetro: es color, o un id de adorno, o solo pinta."""
    if not isinstance(widget, dict):
        return False
    draw = widget.get("draw")
    controls = widget.get("controls")
    if not isinstance(draw, str) or not isinstance(controls, list):
        return False
    ids = [item.get("id") for item in controls if isinstance(item, dict)]
    ids = [kid for kid in ids if isinstance(kid, str)]
    if not ids:
        return False
    if _SEAL.search(draw):
        return True
    if set(ids) <= _DECOR_IDS:
        return True
    read = [kid for kid in ids if _reads_control(draw, kid)]
    return bool(read) and all(_paint_only(draw, kid) for kid in read)


def _dead_control(widget):
    """El slider no entra al draw: el dibujo no puede responder al control."""
    if not isinstance(widget, dict):
        return False
    draw = widget.get("draw")
    controls = widget.get("controls")
    if not isinstance(draw, str) or not isinstance(controls, list):
        return False
    ids = [item.get("id") for item in controls if isinstance(item, dict) and isinstance(item.get("id"), str)]
    if not ids:
        return False
    return not any(_reads_control(draw, kid) for kid in ids)


def verify_widget(claim, widget):
    """Rechaza forma mala, APIs prohibidas, tema cruzado y un enunciado que es una orden."""
    decision = select_claim(claim if isinstance(claim, dict) else {"text": claim or ""})
    reasons = []
    if decision["reason"] == "injection" or _echo(widget):
        reasons.append("injection")
    if decision["reason"] == "slop" or _slop_draw(widget):
        reasons.append("slop")
    if decision["merit"] != "widget":
        reasons.append("no_widget")
    reasons.extend(shape_errors(widget))
    draw = widget.get("draw") if isinstance(widget, dict) else ""
    if banned_in(draw if isinstance(draw, str) else ""):
        reasons.append("banned")
    if network_in(widget):
        reasons.append("network")
    if not _on_claim(decision, widget):
        reasons.append("off_claim")
    if _dead_control(widget):
        reasons.append("dead_control")
    # Una lista estable, sin repetidos, para la tabla de la eval.
    ordered = []
    for reason in reasons:
        if reason not in ordered:
            ordered.append(reason)
    return {
        "accept": not ordered,
        "reasons": ordered,
        "topic": decision["topic"],
        "checks": {
            "on_claim": "off_claim" not in ordered and "no_widget" not in ordered,
            "contract_shape": not any(reason in ordered for reason in (
                "not_object", "extra_keys", "topic", "title", "explain", "draw", "id",
                "questions", "question", "controls", "control",
            )),
            "no_network": "banned" not in ordered and "network" not in ordered,
            "no_injection_obeyed": "injection" not in ordered,
            "not_slop": "slop" not in ordered,
        },
    }
