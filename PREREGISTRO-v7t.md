# Preregistro: v7t, la traslación se vuelve a juzgar

**Escrito el 2026-08-07 a las 15:5x, con v7t en la época 4 de 16 y sin haber
mirado ni una cifra de barrido.** Ese es el sentido de este fichero: el commit
que lo introduce es anterior al resultado, y así el listón no se puede mover
después para que el resultado lo pase.

## Por qué se reabre una línea que estaba cerrada

La traslación **ya se refutó** el `2026-08-06`. v4 = v3 + `--translate 128` dio
mejor `F1` `0.434` frente al `0.415` de v3: **`+0.019`, y el listón pactado antes
era `+0.03`**. A recall igualado v3 era igual o mejor en casi toda la curva. La
página es `traslacion-refutada-v4.md` y la regla se cumplió: línea cerrada.

Reabrirla necesita un motivo que no sea «esta vez seguro que sí», y lo hay:
**aquella comparación se midió sobre Trasancos**, y el mismo `2026-08-06` se
estableció que Trasancos tiene **`86` de sus `93` castros en `train` o `val`, y
solo `7` limpios** (`trasancos-nunca-midio-generalizacion.md`). El banco sobre el
que se refutó la traslación fue invalidado por el propio proyecto horas después.
Un resultado negativo medido con un metro roto no es un resultado negativo: es
una medida que hay que repetir.

Lo que se repite, además, no es lo mismo:

| | v3 → v4 (refutado) | v7 → v7t (ahora) |
|---|---|---|
| corpus | `14.614` viñetas | `15.311`, con negativos agrícolas duros |
| pérdida | entropía cruzada | focal, `gamma 2.0` |
| verdad | catálogo Xunta | fusionado, `+151` de patrimoniogalego |
| banco | Trasancos (`86/93` contaminados) | 4 bloques de Galicia fuera del piloto |

## Lo que sigue siendo cierto de la refutación

Dos cosas de aquella página **no** dependen del banco roto y siguen en pie:

1. **El mecanismo.** Que descentrar hunda los positivos está medido (`0.988 →
   0.386`) y sigue siendo verdad. Lo que no se sostenía es que entrenar con
   desplazamiento lo cure: enseñarle el objeto descentrado le enseña también a
   disparar sobre más cosas, y el intercambio no salía a favor.
2. **El predictor barato.** `eval_checkpoint_descentrado.py` predijo v3 > v4
   antes de barrer, y el barrido le dio la razón. Cuesta minutos en vez de dos
   horas.

## La regla, escrita antes de mirar

**Métrica primaria**: media de `F1` sobre los cuatro bloques —Lugo, A Coruña,
Ourense, Pontevedra— con el metro fusionado y umbral `0.70`, que es exactamente
como está medido v7.

Referencia de v7, ya publicada y no revisable:

| bloque | precisión | F1 |
|---|---:|---:|
| Lugo | `0.826` | `0.697` |
| A Coruña | `0.769` | `0.396` |
| Ourense | `0.543` | `0.535` |
| Pontevedra | `0.391` | `0.419` |
| **media** | `0.632` | **`0.512`** |

**El listón es el mismo que se le puso a v4: `+0.03`.** No se rebaja por haber
reabierto la línea.

- **`F1` medio de v7t `>= 0.542`** → la traslación aporta sobre banco limpio, y
  lo que estaba mal era el banco, no la idea. Entra en el modelo de producción.
- **`F1` medio de v7t `< 0.542`** → **la traslación queda refutada por segunda
  vez, ahora sobre banco válido, y la línea se cierra definitivamente.** No se
  vuelve a abrir sin un mecanismo nuevo, no con otro corpus.

**Sin excepciones por bloque.** Si v7t gana en Pontevedra y pierde en los otros
tres, pierde. Un solo bloque a favor es exactamente la forma que tiene el ruido
de parecer un hallazgo: `n` va de `36` a `75` castros por bloque, y con esa
anchura un bloque suelto no distingue nada.

**Orden de ejecución, para no pagar de más**: primero
`eval_checkpoint_descentrado.py` sobre `cls-v7t/best.pt` y `cls-v7/best.pt`.
Cuesta minutos. Si predice v7t por debajo de v7, se anota como corroboración
—no como decisión: la decisión la toma el barrido, que es la métrica primaria—
y el barrido se ejecuta igual, porque esta vez lo que se juzga es el banco nuevo.

## Qué se hace con el resultado, gane o pierda

Va al preprint en los dos casos. Un resultado negativo con la regla escrita antes
y el banco arreglado vale más que el positivo pequeño que se habría podido
fabricar moviendo el listón.
