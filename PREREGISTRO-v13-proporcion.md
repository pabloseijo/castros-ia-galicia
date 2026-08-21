# Preregistro: v13, la proporción y no la cantidad

**Escrito el 2026-08-09 a las 12:5x, con el veredicto de v11p ya conocido
(`0,390` contra `0,512` de v7) y sin ninguna cifra de v13.**

## La hipótesis, en una frase

**v11p falló por la proporción de positivos, no por tener demasiados.** Si es
cierto, bajar la proporción al nivel de v7 **sin quitar el fondo** debe recuperar
el rendimiento, y usando más positivos que v7.

## De dónde sale

Medido:

| | positivos en train | despliegue | desajuste | `F1` medio |
| --- | ---: | ---: | ---: | ---: |
| v7 | `8,9%` | `0,73%` | `12×` | **`0,512`** |
| v11p | `26,7%` | `0,73%` | `37×` | `0,390` |

Y v11p es peor **a todos los umbrales** —a recall `0,714`, precisión `0,363`
contra `0,703`—, así que no es calibración: separa peor. La causa es que aprende
un mundo donde uno de cada cuatro sitios es un yacimiento.

Kapoor y Narayanan (`10.1016/j.patter.2023.100804`) lo llaman **L3.3, sesgo de
muestreo en la distribución de test**; aquí además el sesgo está en el
entrenamiento.

## Qué se hace, y por qué es barato

**Se submuestrean los positivos del corpus de v11p hasta el `8,9%` de v7**, sin
tocar el fondo y **sin cortar una sola viñeta nueva**: es un cambio de índice
sobre arrays que ya existen, enlazados desde el corpus de v11p.

> **Corrección hecha al ejecutarlo, antes de entrenar.** Este preregistro predijo
> `~1.263` positivos. El número real es **`1.016`**, porque el fondo de v11p
> (`10.401`) es menor que el de v7 (`11.064`) y la proporción se calcula sobre él.
> Eso cambia lo que mide el experimento y hay que decirlo:

| | positivos en train | fondo | proporción | bloques con positivos |
| --- | ---: | ---: | ---: | ---: |
| v7 | `1.072` | `11.064` | `8,9%` | — |
| **v13** | **`1.016`** | `10.401` | `8,9%` | **`904`** |
| v11p | `3.795` | `10.401` | `26,7%` | — |

Así que v13 **no tiene más positivos que v7: tiene los mismos y a la misma
proporción**. Lo que cambia es de dónde salen — se sortean de un fondo `3,5×`
mayor, estratificados por bloque, y quedan repartidos en `904` bloques.

La variable que queda aislada es entonces **la cobertura geográfica de los
positivos**, no su cantidad. Sigue siendo un experimento legítimo y con la misma
lógica —¿era la proporción?— pero mide algo más estrecho de lo que se escribió.

## El listón

Referencia: **v7 = `0,512`** de `F1` medio sobre los cuatro bloques, al umbral
preregistrado `0,70`.

- **Hipótesis confirmada**: `F1` medio **`≥ 0,512`**. La proporción era la causa,
  y más positivos a la proporción correcta no hacen daño.
- **Confirmada y además útil**: `≥ 0,542` (el `+0,03` habitual). Entonces el dato
  sí suma, pero solo si se sirve en la proporción adecuada.
- **Refutada**: `< 0,512`. Si con la proporción de v7 sigue por debajo de v7, la
  causa no era la proporción y hay que buscarla en otro sitio —candidatos: la
  calidad de los positivos nuevos, o la fuga L1.4 recién detectada—.

## Lo que se controla

1. **Mismo fondo, mismas viñetas, mismos arrays.** Solo cambia qué positivos
   entran en `train`.
2. **El examen no se toca**: se hereda de v7 como en v11p. Su desequilibrio
   (`1,6:1`) ya está declarado y **no se usa para elegir el checkpoint**: la
   selección será por `selection_best` como siempre, pero **el veredicto es el
   barrido**, no la métrica interna. Esa lección ya costó un día.
3. **Dedup L1.4 activo**: el build ahora mueve al split de su gemelo cualquier
   viñeta a menos de `100 m`. v11p se entrenó sin eso.
4. **Precinto de Portugal**, verificado por `controles_v11.py`.

## La predicción, escrita antes

Que v13 quede **entre `0,50` y `0,55`**: recupera lo de v7 y quizá algo más por
tener un `63%` más de positivos. Si sale por encima de `0,57` habría que
desconfiar y buscar fuga antes de celebrarlo.

## Coste

Un entrenamiento (`~2,5 h`) y cuatro barridos (`~4 h`). **Cero cortes**: todo se
reutiliza del corpus de v11p.
