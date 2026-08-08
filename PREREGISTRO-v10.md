# Preregistro: v10, minería de falsos positivos con peso real

**Escrito el 2026-08-08 a las 11:4x, con v9 entrenando y sin ninguna cifra de v10.**
Cuarto preregistro de la serie, mismo listón que los tres anteriores.

## El diagnóstico, con números

El cuello medido es la **precisión**: `0.826` en Lugo contra `0.391` en
Pontevedra, y la media de `F1` en `0.512`. El dictamen de revisión lo puso como
cuello principal de modelo, y señaló que la palanca de Canedo —minería de
negativos duros, que les llevó de `5.678` detecciones a `40`— **seguía sin
ejecutarse a fondo**.

La sesión del `2026-08-06` ya lo intentó: v6 añadió `534` negativos duros y
«movió poco». Pero el diagnóstico de por qué está escrito y nunca se actuó sobre
él: **el entrenamiento los diluía**. El corpus de v7 tiene

| grupo | n |
|---|---:|
| `random_terrain` | `10.742` |
| `hard_negative_moderno` | `534` |
| `hard_negative_agricola` | `163` |

o sea, los duros son el **`3,8%` de la clase fondo**, y todos entran con el mismo
peso de clase `0.366`. El modelo ve veinte veces más negativos fáciles que
difíciles y los trata igual. No es que los negativos duros no sirvan: es que no
se oían.

## Lo que cambia v10, y solo eso

1. **Se minan los falsos positivos reales de los cuatro barridos de v7**: `1.306`
   celdas por encima de `0.5` que no caen sobre castro catalogado ni sobre la
   máscara. No son negativos inventados — son las equivocaciones medidas del
   modelo en despliegue.
2. **Pesan.** `--peso-negativo-duro 8`: verificado sobre GPU que un negativo duro
   pasa de aportar el `12%` de un lote de ocho al `53%`. La pérdida focal hace
   media **ponderada**, no simple; con media simple el peso se diluiría en el
   tamaño del lote y no haría nada.

Todo lo demás es idéntico a v7: mismo encoder, misma pérdida focal `gamma 2.0`,
mismos `splits`, mismo umbral de evaluación.

## La cautela que hace esto legítimo

**Un falso positivo del barrido puede ser un castro inédito** — es literalmente
lo que el proyecto busca. Meterlo como negativo enseñaría al modelo a no
encontrar lo que se le pide.

Mitigación: se excluyen de la minería los candidatos que la revisión visual marcó
como prometedores o dudoso-prometedores. Y se asume el riesgo residual
conscientemente: a umbral `0.5` la precisión medida por bloque va de `0,082` a
`0,230`, así que entre el `77%` y el `92%` de lo minado es error real. **El riesgo
queda escrito, no escondido**, y la lista minada se conserva para poder auditarla.

## La regla, escrita antes de mirar

**Métrica primaria**: media de `F1` sobre los cuatro bloques a umbral `0.70` con
el metro fusionado. Referencia v7: **`0.512`**.

**Listón: `+0.03` → `F1` medio `>= 0.542`.** El mismo que v4, v7t, v8 y v9, y por
la misma razón: en v4 se midió que un `+0.019` no se distingue de cero con `n` de
`36` a `75` castros por bloque.

- **`>= 0.542`** → la minería con peso funciona. Entra en producción y **se
  convierte en el procedimiento estándar**: cada barrido alimenta el siguiente.
- **`< 0.542`** → queda refutada *con este peso y esta cantidad*, y la línea de
  «más y mejores negativos» se cierra salvo mecanismo nuevo.

**Sin excepciones por bloque.**

## Medida secundaria, que no decide

La hipótesis es específica sobre **precisión**. Así que se mirará aparte la
precisión media de los cuatro bloques —hoy `0.632`— y en particular la de
Pontevedra, hoy `0.391` y la peor. Si el `F1` medio no llega pero la precisión
sube claramente, v10 queda refutado igual y se escribe el detalle: significaría
que la minería hace lo que promete y que el `F1` lo esconde porque el recall
paga la factura.

## Qué se hace con el resultado

Va al preprint gane o pierda, como los otros cuatro.
