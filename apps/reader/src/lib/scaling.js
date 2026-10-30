// Ilustración de la tensión Kaplan frente a Chinchilla (RRM-8 A). Solo usa lo citado:
// - exponentes de N_óptimo ∝ C^a: 0.73 (Kaplan) y 0.50 (Chinchilla), citados del abstract de Pearce y Song;
// - la relación FLOPs ≈ 6·N·D (Chinchilla §3), de la que D_óptimo ∝ C^(1−a).
// No es una predicción propia. Con N sin embeddings (Kaplan) la relación 6ND es aproximada.

/** Factor por el que crece el tamaño óptimo del modelo cuando el cómputo se multiplica por x. */
export const modelGrowth = (x, a) => Math.pow(x, a);

/** Factor por el que crecen los tokens óptimos (D = C / 6N  =>  D ∝ C^(1−a)). */
export const tokenGrowth = (x, a) => Math.pow(x, 1 - a);

/** Comprobación: el producto N·D debe crecer como el cómputo (FLOPs ≈ 6ND). */
export const computeGrowth = (x, a) => modelGrowth(x, a) * tokenGrowth(x, a);
