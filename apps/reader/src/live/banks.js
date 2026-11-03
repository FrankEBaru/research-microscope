// Question bank copied from RRM-78 so the mark word stays in the explain.

function qs(rows) {
  return rows.map(([q, why]) => ({ q, why }));
}

export const BANKS = {
  positional_encoding: {
    explain: "Cada par de dimensiones es una onda. La base cambia qué tan rápido gira: las primeras vuelven seguido y las últimas casi no se mueven, así que una posición larga sigue viéndose distinta.",
    questions: qs([
      ["¿Por qué una base más grande hace más lentas las dimensiones altas?", "la base está en el exponente de la frecuencia"],
      ["¿Qué se confunde si todas las ondas van igual de rápido?", "la posición deja de separarse entre dimensiones"],
      ["¿Cómo cabe una frase larga en un seno y un coseno?", "las frecuencias bajas dan vueltas despacio"],
    ]),
  },
  softmax_temperature: {
    explain: "La temperatura parte los logits antes del softmax. Baja, y casi toda la masa cae en la opción más alta; alta, y las opciones se parecen.",
    questions: qs([
      ["¿Por qué bajar la temperatura vuelve una sola opción casi segura?", "el softmax se concentra en el logit mayor"],
      ["¿Qué queda de la distribución si la temperatura es muy alta?", "las opciones se acercan"],
      ["¿Qué se está moviendo: los logits o las palabras?", "el control parte los logits"],
    ]),
  },
  attention_scale: {
    explain: "El producto QK crece con la dimensión. Dividir entre la raíz de d_k deja el softmax en una zona donde más de una clave todavía pesa.",
    questions: qs([
      ["¿Por qué se divide entre la raíz de d_k y no entre d_k?", "la varianza del producto es d_k, no d_k al cuadrado"],
      ["¿Qué le pasa al softmax si el producto crece con la dimensión?", "una sola clave se queda con el peso"],
      ["¿Cómo se reparte el peso de una clave con y sin esa división?", "el dibujo muestra las dos filas"],
    ]),
  },
  stddev: {
    explain: "La desviación estándar es el ancho de la nube alrededor de la media. Al dividir entre sigma, puntos lejanos y cercanos quedan en la misma escala.",
    questions: qs([
      ["¿Qué cambia en los puntos si subo la desviación estándar?", "la nube se abre alrededor de la media"],
      ["¿Por qué dividir entre sigma los pone en la misma escala?", "se quita el ancho de la nube"],
      ["¿Qué tan lejos de la media queda un punto cuando sigma es chico?", "la misma distancia numérica pesa más"],
    ]),
  },
  rope: {
    explain: "RoPE gira el par de coordenadas de cada posición por un ángulo. La posición no se suma: queda en el ángulo, y dos tokens se comparan por cuánto se giraron.",
    questions: qs([
      ["¿Por qué girar un vector guarda la posición?", "el ángulo depende del índice del token"],
      ["¿Qué pasa con el ángulo si los tokens quedan más lejos?", "la diferencia de giros crece"],
      ["¿En qué se distingue esto de sumar un seno al embedding?", "aquí la posición es una rotación"],
    ]),
  },
  dpo_beta: {
    explain: "Beta dice cuánto puede alejarse la política nueva de la de referencia. Chico, y el modelo persigue el premio aunque se desvíe; grande, y se queda cerca.",
    questions: qs([
      ["¿Por qué un beta chico deja que la política se aleje más?", "el freno contra la referencia pesa menos"],
      ["¿Qué se está frenando: el premio o la distancia a la referencia?", "beta pesa esa distancia"],
      ["¿Cómo se ve el premio implícito si subo beta?", "el log-ratio se encoge"],
    ]),
  },
  yarn_scale: {
    explain: "YaRN cambia la escala de las frecuencias de RoPE para un contexto más largo que el de entrenamiento. Al estirar la escala, las vueltas que cubrían el entrenamiento ahora cubren más tokens.",
    questions: qs([
      ["¿Por qué hay que reescalar RoPE si el contexto crece?", "sin escala el ángulo se sale de lo entrenado"],
      ["¿Qué se deforma en las frecuencias altas al estirar la escala?", "las vueltas rápidas se comprimen"],
      ["¿Qué se alarga: el texto o las vueltas del ángulo?", "el control mueve la escala, no el texto"],
    ]),
  },
  spec_cost: {
    explain: "El borrador propone varios tokens y cada uno tiene un costo. Se aceptan con la chance del acuerdo. La curva es el speedup según el largo; el punto verde es el largo que más conviene. Si el costo sale caro, queda por debajo de 1.",
    questions: qs([
      ["¿Por qué no proponer cincuenta tokens de borrador?", "cada uno cuesta, y el ahorro deja de subir"],
      ["¿Qué es el costo c del dibujo?", "la fracción de un paso del modelo grande"],
      ["¿Por qué la curva puede quedar por debajo de 1?", "un borrador caro y poco aceptado sale más lento"],
    ]),
  },
  speculative: {
    explain: "El modelo chico propone un borrador y el grande lo acepta token por token. Si se parecen, la racha aceptada crece y se ahorran pasos del modelo grande.",
    questions: qs([
      ["¿Por qué un borrador parecido alarga la racha aceptada?", "el grande confirma varios tokens de un jalón"],
      ["¿Qué se paga cuando el modelo grande rechaza un token?", "se tira el resto del borrador"],
      ["¿Dónde se gana tiempo: en proponer o en verificar?", "verificar un bloque sale más barato que generarlos"],
    ]),
  },
  noise_schedule: {
    explain: "Cada paso del proceso directo suma ruido según beta_t. Si beta crece rápido, la imagen se pierde en pocos pasos; si crece lento, la señal aguanta más.",
    questions: qs([
      ["¿Por qué un beta_t grande borra la imagen más pronto?", "cada paso mete más ruido"],
      ["¿Qué queda de la señal a la mitad del horario de ruido?", "depende de qué tan rápido creció beta"],
      ["¿Qué se está moviendo: el paso o la cantidad de ruido?", "el control es la cantidad de ruido del paso"],
    ]),
  },
  guidance: {
    explain: "La guía sin clasificador empuja la muestra hacia el texto restando la predicción sin condición. Sube la escala y el texto manda más; bájala y la imagen se parece al modelo sin prompt.",
    questions: qs([
      ["¿Por qué subir la escala pega más la imagen al texto?", "se amplifica la diferencia contra el modelo sin prompt"],
      ["¿Qué se pierde cuando la guía es demasiado alta?", "la muestra se sale de lo que el modelo sabe pintar"],
      ["¿Qué se está restando: la predicción con texto o la que va sin él?", "a la condicionada se le resta la otra"],
    ]),
  },
  detr_match: {
    explain: "Cada query se empareja con una sola caja. El costo mezcla clase y caja; si sube el peso de la clase, el emparejamiento prefiere la etiqueta aunque la caja quede peor.",
    questions: qs([
      ["¿Por qué cada query termina con una sola caja?", "el emparejamiento es uno a uno"],
      ["¿Qué cambia en el emparejamiento si pesa más la clase que la caja?", "gana la etiqueta aunque la caja se desplace"],
      ["¿Qué es el costo: la etiqueta, la posición, o las dos?", "el control mezcla las dos"],
    ]),
  },
  residual: {
    explain: "El atajo suma la entrada del bloque con lo que el bloque calculó. Si se apaga, la señal tiene que cruzar la capa entera y se aplana más fácil.",
    questions: qs([
      ["¿Por qué sumar la entrada evita que la señal se aplaste?", "una parte cruza el bloque sin transformarse"],
      ["¿Qué le pasa al gradiente si quito el atajo?", "tiene que atravesar todas las capas"],
      ["¿Qué se está viendo: la entrada, la salida del bloque, o la suma?", "el control mezcla entrada y salida"],
    ]),
  },
  nucleus: {
    explain: "Top-p se queda con el conjunto más chico de tokens cuya masa pasa de p. Bajas p y el conjunto se encoge a lo más seguro; lo subes y entran palabras más raras.",
    questions: qs([
      ["¿Por qué bajar p deja menos palabras posibles?", "la masa acumulada se llena antes"],
      ["¿En qué se distingue esto de cortar a un número fijo de opciones?", "el tamaño del conjunto depende de la masa"],
      ["¿Qué se está moviendo: la masa acumulada o el orden de los logits?", "p corta la masa, el orden no cambia"],
    ]),
  },
  contrastive_temp: {
    explain: "En el contraste, la temperatura parte las similitudes antes del softmax. Baja, y el positivo se queda con el lote; alta, y positivos y negativos se parecen.",
    questions: qs([
      ["¿Por qué una temperatura baja aplasta el lote en el positivo?", "el softmax se vuelve casi seguro"],
      ["¿Qué se confunde si la temperatura es muy alta?", "positivos y negativos pesan parecido"],
      ["¿Qué se está escalando: las similitudes o las etiquetas?", "solo las similitudes entran al softmax"],
    ]),
  },
  rope_relative: {
    explain: "RoPE gira q y k con la posición absoluta. Desplaza los dos el mismo tramo: las flechas avanzan juntas y el producto no se mueve, la curva queda plana. Cambia la distancia m−n y el producto sí cambia. El giro es absoluto; el puntaje es relativo.",
    questions: qs([
      ["¿Por qué un giro absoluto termina comparando distancias?", "los dos giros se restan en el producto"],
      ["¿Qué pasa con el puntaje si corro la frase entera?", "el desplazamiento mueve las flechas y no el producto"],
      ["¿Para qué sirven varias velocidades de giro?", "cada par mira otra escala de distancia"],
    ]),
  },
  adam: {
    explain: "Adam guarda dos momentos: hacia dónde empuja el gradiente y qué tan brusco es cada eje. En un valle angosto el segundo momento crece en la pared y achica ese paso. SGD, con el mismo lr, zigzaguea; si subes lr, se sale.",
    questions: qs([
      ["¿Por qué SGD rebota en un valle angosto y Adam no?", "el segundo momento achica el eje empinado"],
      ["¿Qué se está promediando: la dirección o el tamaño del paso?", "los dos momentos, uno para cada cosa"],
      ["¿Qué pasa si subo el lr y el valle sigue igual de angosto?", "SGD se sale y Adam aguanta más"],
    ]),
  },
  lora: {
    explain: "LoRA escribe el cambio de pesos como una suma de productos externos, uno por cada rango. Cada rango agrega un patrón. El tablero es un ejemplo chico; el conteo es el de una capa 4096×4096: 2dr parámetros, no d al cuadrado.",
    questions: qs([
      ["¿Por qué un rango chico puede cambiar una matriz enorme?", "cada rango es un solo patrón, un producto externo"],
      ["¿Qué se agrega cuando el rango pasa de 2 a 3?", "aparece el patrón que faltaba y el error baja"],
      ["¿Cuántos números nuevos son, frente a reentrenar la capa?", "2dr contra d al cuadrado"],
    ]),
  },
  kl_rlhf: {
    explain: "RLHF maximiza el premio menos beta por el KL contra la referencia. La política óptima es la referencia por e elevado al premio sobre beta. Con beta chico el KL ya no frena y toda la masa cae en el token de más premio.",
    questions: qs([
      ["¿Por qué no quedarse siempre con el token de más premio?", "el KL lo cobra si se aleja de la referencia"],
      ["¿Qué le pasa a la política si beta se acerca a cero?", "se concentra en un solo token"],
      ["¿Qué se está viendo: el premio, la referencia, o las dos?", "la política mezcla las dos"],
    ]),
  },
  beam: {
    explain: "La búsqueda por haz guarda varios prefijos, no solo el primero. Con ancho 1 es codiciosa y cae en «el día», que empezó bien y termina mal. Con un haz de 2 sobrevive «un gato», peor al inicio y mejor al final.",
    questions: qs([
      ["¿Por qué no elegir siempre la palabra más probable?", "un prefijo alto puede no tener buena continuación"],
      ["¿Qué cambia cuando el ancho del haz pasa de 1 a 2?", "entra el prefijo que parecía peor"],
      ["¿Qué se está comparando: el primer token o la frase completa?", "el haz se queda con el mejor total de los que guardó"],
    ]),
  },
  batchnorm: {
    explain: "BatchNorm resta la media del lote y divide entre su desviación. Mueve la escala o el corrimiento de la entrada: la fila de arriba cambia y la del medio no. Gamma y beta, aprendidos, vuelven a estirar y a mover la salida.",
    questions: qs([
      ["¿Por qué la fila de en medio no se entera de la escala?", "restar la media y dividir cancela ese cambio"],
      ["¿Para qué están gamma y beta si ya normalicé?", "la red todavía puede pedir otra escala"],
      ["¿Qué se mueve cuando corro la entrada y qué se queda?", "solo la fila cruda; las otras usan el lote normalizado"],
    ]),
  },
  chinchilla: {
    explain: "Con un cómputo fijo, un modelo más grande deja menos datos. La curva es el ajuste de Chinchilla en ese trueque; el punto marca el fondo. Si crece el presupuesto, el valle se corre y conviene subir datos junto con el modelo.",
    questions: qs([
      ["¿Con más cómputo, crezco el modelo o los datos?", "los dos, el valle no se va a un extremo"],
      ["¿Por qué hay un tamaño mejor para un presupuesto fijo?", "pasar de ese tamaño quita datos que hacían falta"],
      ["¿De dónde sale la forma de la curva?", "del ajuste publicado, no de una corrida de este demo"],
    ]),
  },
  moe: {
    explain: "El router manda cada token a unos pocos expertos. El cupo es corto: si muchos eligen al mismo, los que llegan tarde se caen. Con k = 2, el segundo experto todavía los puede recibir.",
    questions: qs([
      ["¿Por qué un experto popular deja tokens afuera?", "el cupo se llena y los de después se caen"],
      ["¿Qué recupera el top 2 que el top 1 tira?", "el segundo experto todavía tiene lugar"],
      ["¿Qué se está limitando, el puntaje o el cupo?", "el cupo; el puntaje solo elige a quién"],
    ]),
  },
  gqa: {
    explain: "El cache guarda K y V por grupo. Crece con los tokens y con los grupos que no comparten esa memoria. Menos grupos, y el mismo texto ocupa menos.",
    questions: qs([
      ["¿Por qué un texto largo se come la memoria?", "cada token suma K y V en cada capa"],
      ["¿Qué se achica si las cabezas comparten K y V?", "el cache, no la cantidad de tokens"],
      ["¿Qué marca la raya del medidor?", "un cupo fijo de celdas, para ver cuándo se pasa"],
    ]),
  },
  quant: {
    explain: "absmax arma el paso con el valor más grande. Un outlier lo agranda y el error se come a los números chicos. Si ese outlier se queda afuera del paso, el resto vuelve a tener niveles finos.",
    questions: qs([
      ["¿Por qué un solo número grande arruina a los chicos?", "el paso sale de ese máximo"],
      ["¿Qué pasa con el error si ese número se queda afuera?", "el paso se mide con el resto y baja"],
      ["¿Qué se redondea cuando el interruptor está prendido?", "los chicos; el outlier se queda como estaba"],
    ]),
  },
  online_softmax: {
    explain: "El softmax puede llegar por bloques. De cada bloque quedan el máximo y la suma; si el máximo sube, la suma vieja se reescala. Con los 4 bloques el resultado es exacto: cae sobre el softmax de la lista completa.",
    questions: qs([
      ["¿Cómo se calcula el softmax sin ver todos los puntajes?", "con el máximo y la suma, que se corrigen al llegar más"],
      ["¿Por qué se multiplica la suma vieja cuando aparece un máximo mayor?", "los exponenciales de antes quedaron en otra escala"],
      ["¿El resultado por bloques es aproximado o exacto?", "al ver todos los bloques coincide con el softmax completo"],
    ]),
  },
  ssm_delta: {
    explain: "En un modelo selectivo, delta decide si el estado se queda o se reinicia. Delta grande en un pico lo graba. Delta chico en el resto no lo borra. Si el resto también tiene delta grande, el estado olvida el pico.",
    questions: qs([
      ["¿Por qué un delta grande en el pico deja una meseta?", "ese paso reemplaza el estado con el pico"],
      ["¿Qué pasa si el delta del resto también sube?", "los ceros de en medio borran lo grabado"],
      ["¿En qué se distingue esto de acordarse de todo?", "solo se queda lo que el delta elige"],
    ]),
  },
  smoothquant: {
    explain: "SmoothQuant pasa el outlier de las activaciones a los pesos. El canal se divide por s y la fila de pesos se multiplica por s, así que el producto no cambia. En alfa 0.5 las dos filas se encuentran.",
    questions: qs([
      ["¿Por qué el producto del canal no cambia?", "lo que se le quita a la activación se le pone al peso"],
      ["¿Qué se pone difícil si alfa llega a 1?", "el outlier se fue entero a los pesos"],
      ["¿Por qué 0.5 es el punto de la figura?", "ahí las dos filas quedan parejas"],
    ]),
  },
  yarn_parts: {
    explain: "YaRN por partes no estira todas las frecuencias. Si la longitud de onda ya cabe muchas veces en el contexto, esa parte se queda. Si es más larga que el contexto, se divide entre la escala. En medio, se mezcla. Alfa 1 y beta 32 son los de Llama.",
    questions: qs([
      ["¿Por qué no se estiran las frecuencias rápidas?", "ya dieron varias vueltas dentro del contexto"],
      ["¿Qué parte sí se divide entre la escala?", "la cuya onda es más larga que el contexto"],
      ["¿Qué marcan alfa 1 y beta 32?", "dónde empieza y dónde termina la mezcla"],
    ]),
  },
};

export function knob(id, label, min, max, value, step) {
  return { id, label, min, max, value, step };
}

export function widget(topic, id, title, controls, draw, copy) {
  const bank = BANKS[topic];
  return {
    id,
    topic,
    title,
    explain: copy && copy.explain ? copy.explain : bank.explain,
    questions: copy && copy.questions ? copy.questions : bank.questions,
    controls,
    draw: draw.trim(),
  };
}
