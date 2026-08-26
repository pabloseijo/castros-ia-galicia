# Preregistro: el peso de los negativos duros, barrido en `2` y `4`

**Escrito el 2026-08-09 a las 12:xx, con los barridos de v11p a medias —Lugo por
`1.993` filas de `~8.500`— y sin ninguna cifra de este experimento.** Es el
experimento `3` de la lista cerrada de [[plan-hasta-romper-el-precinto]].

## Qué se prueba y por qué NO es repetir v10

v10 puso el peso de los negativos duros en `8` y **fracasó de forma instructiva**:
el recall de castro se hundió de `0,722` a `0,256` y en O Val cayó a `0,000`. El
modelo no aprendió a distinguir mejor: aprendió a **no arriesgar**, y cambió
castros por mámoas.

Pero eso refuta **el peso `8`**, no la palanca. Canedo et al. pasaron de `5.678`
detecciones a `40` con minería de negativos duros, y lo hicieron **con dos
arqueólogos revisando en el bucle**, no con un multiplicador fijo. El error de v10
fue elegir **un solo valor sin escala**, que es justo lo que un preregistro debe
impedir.

Aquí se barre el peso: **`1` (control), `2` y `4`**.

## El diagnóstico que hay que vigilar

El fracaso de v10 tiene una firma clara, y es la que decide si un peso es
aceptable **antes** de mirar el `F1`:

> **Si el recall de castro en validación baja de `0,70`, el peso está de más**,
> por bueno que salga cualquier otra cifra. Un modelo que deja de ver castros no
> sirve para buscar castros, y la precisión que gana a cambio es la de no mirar.

v11p, la referencia actual, tiene recall de castro `0,861`.

## El listón

Referencia: **v11p**, con su `F1` medio sobre los cuatro bloques —pendiente de los
barridos en curso; **este preregistro se cierra sin conocerlo**, que es la
condición para que valga—.

- **Éxito**: `+0,03` de `F1` medio sobre v11p **y** recall de castro `≥ 0,70`.
  Las dos condiciones, no una.
- **Fracaso**: cualquier otra cosa. Y si el patrón de v10 se repite —precisión
  arriba, recall de castro abajo— **la palanca queda refutada en todo su rango
  útil** y no se vuelve a ella.

El `+0,03` es el mismo listón de v4, v7t, v8, v9 y v10: con `n` de `36` a `75`
castros por bloque, en v4 se midió que un `+0,019` no se distingue de cero.

## Lo que hay que controlar para que la comparación valga

1. **Mismo corpus que v11p**, cambiando solo `--peso-negativo-duro`. Nada más.
2. **Mismo examen**: el conjunto de validación no se toca. Si cambiara,
   `selection_best` deja de ser comparable y con él la regla de cribado.
3. **El precinto de Portugal**, comprobado por `controles_v11.py` antes de
   entrenar. El `2026-08-09` esa guarda cazó `65` castros sellados a `0 m` dentro
   del conjunto de entrenamiento; sin ella, la única medición insesgada del
   proyecto habría nacido contaminada.

## La predicción, escrita antes

Con la regla de cribado —el corte de `0,40` en `selection_best` mata candidatos,
pero **no ordena por encima de él**—, la predicción es que **`2` y `4` queden
entre `0,80` y `0,86`**, o sea indistinguibles de v11p por la métrica interna, y
que la diferencia solo aparezca en el barrido.

Si alguno cae por debajo de `0,40`, **no se barre**: se ahorra `9,5 h` por
hipótesis muerta.

## Coste

Dos entrenamientos de `~2,5 h` más sus barridos. **No se lanzan hasta que
terminen los barridos de v11p**: en un nodo de `7,3 GB` cabe un trabajo pesado y
poco más, y hoy se han perdido tres barridos por ignorarlo.
