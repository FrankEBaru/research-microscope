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


# Orden = desempate. El más específico va primero.
TOPICS = (
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
            "las primeras vuelven seguido y las últimas casi no se mueven, así que una posición larga sigue viéndose distinta."
        ),
        "questions": (
            ("¿Por qué una base más grande hace más lentas las dimensiones altas?", "la base está en el exponente de la frecuencia"),
            ("¿Qué se confunde si todas las ondas van igual de rápido?", "la posición deja de separarse entre dimensiones"),
            ("¿Cómo cabe una frase larga en un seno y un coseno?", "las frecuencias bajas dan vueltas despacio"),
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
            "RoPE gira el par de coordenadas de cada posición por un ángulo. "
            "La posición no se suma: queda en el ángulo, y dos tokens se comparan por cuánto se giraron."
        ),
        "questions": (
            ("¿Por qué girar un vector guarda la posición?", "el ángulo depende del índice del token"),
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
    """Draw de oro solo para los cuatro temas con few-shot. Los otros temas esperan a RRM-80."""
    decision = select_claim(claim)
    if decision["merit"] != "widget":
        return None
    return gold_widget(decision["topic"])


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


def verify_widget(claim, widget):
    """Rechaza forma mala, APIs prohibidas, tema cruzado y un enunciado que es una orden."""
    decision = select_claim(claim if isinstance(claim, dict) else {"text": claim or ""})
    reasons = []
    if decision["reason"] == "injection" or _echo(widget):
        reasons.append("injection")
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
        },
    }
