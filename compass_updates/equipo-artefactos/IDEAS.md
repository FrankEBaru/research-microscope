# Ideas — equipo artefactos

## RRM-78 (en curso)

- Un widget solo si hay un parámetro que se puede mover y ver. BLEU, “10× smaller” y “8× deeper” no entran, aunque el papel sea famoso.
- La inyección en el enunciado gana sobre la fórmula: se va a `skip` y el verificador rechaza el widget aunque el draw sea el de oro.
- `attention_scale` aunque el enunciado diga “dividir entre d_k”. El few-shot dibuja las dos filas (sin dividir y entre la raíz). No se inventa una tercera fórmula.
- YaRN gana sobre RoPE si el enunciado trae las dos cosas. El contraste gana sobre la temperatura del softmax si el enunciado es de contraste.
- “Residual nets are 8x deeper” es un resultado, no el atajo. El atajo solo si el enunciado habla de residual connection / identity mapping.
- Los cuatro draws de oro viven en `rrm/liveart/fewshots.py` para que RRM-80 los sustituya sin tocar el prompt a mano.
