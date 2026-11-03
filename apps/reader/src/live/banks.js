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
};

export function knob(id, label, min, max, value, step) {
  return { id, label, min, max, value, step };
}

export function widget(topic, id, title, controls, draw) {
  const bank = BANKS[topic];
  return {
    id,
    topic,
    title,
    explain: bank.explain,
    questions: bank.questions,
    controls,
    draw: draw.trim(),
  };
}
