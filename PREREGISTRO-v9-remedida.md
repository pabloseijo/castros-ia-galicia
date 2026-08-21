# Preregistro — la remedida de v9

**Escrito el 2026-08-10 a las 12:55, con los barridos ya corriendo y ANTES de
ver una sola cifra nueva.** Pontevedra iba por `949` de `6.877` filas y los
otros tres bloques no habían empezado.

## Por qué hay una remedida

v9 —relieve más ortofoto, `7` canales— se dio por refutada el `2026-08-08` con
`F1 0,222` en Lugo contra `0,697` de v7. El `2026-08-10` se descubrió que **ese
número no medía a v9**: su barrido cubría `2.100` de las `8.572` celdas del
bloque, y un castro que el barrido no alcanza cuenta como fallo del modelo sin
serlo. Ningún bloque tenía barrido completo: `0` de `4`.

La causa era única y está arreglada: `map(chunksize=100)` retiene los
resultados de `100` tareas en el obrero, `4,4 GB` con `7` canales contra `1,9`
con `3`. Por eso murió **solo** v9.

## Lo que se va a hacer

Los cuatro barridos de v9 completos, con el mismo checkpoint `data/cls-v9/best.pt`
—**no se reentrena nada**—, la misma rejilla, la misma verdad de campo y la
misma máscara que usan v7 y los demás. Lugo y Pontevedra reanudan sobre sus
filas existentes, que se verificaron celda a celda contra la rejilla de v7:
`2.100` y `732` coincidencias exactas de `id` y coordenadas.

## Las hipótesis, con lo que ya se sabe

**H0 — v9 no bate a v7.** Es lo que espero, y no por inercia: hay una medida
independiente del barrido que lo predice. Comparadas las ortofotos de `260`
castros contra `260` de terreno aleatorio, el mayor efecto discriminante es
`0,534` sobre un azar de `0,500`. **La ortofoto no distingue un castro de un
trozo de monte**, así que sus tres canales entran como casi-ruido en una red
que concatena.

**H1 — v9 bate a v7.** Sería la sorpresa, y obligaría a revisar la medida
espectral: si tres canales casi-aleatorios ayudan, o la medida está mal
planteada o el modelo extrae algo que ese descriptor no captura.

## El listón, que es el de siempre y no se mueve

> **`F1 ≥ 0,542` de media en los cuatro bloques** —`+0,03` sobre el `0,512` de
> v7— **y recall de castro `≥ 0,70`.**

Y una condición añadida el `2026-08-09` tras aprenderla por las malas: si v9
gana, hay que comprobar además con `conjunto_no_pierde.py` que **no pierde
castros que el conjunto congelado sí encontraba**. Un modelo que sube el `F1`
medio perdiendo hallazgos no es mejor para lo que sirve esto.

## Lo que se declara de antemano para no poder elegirlo después

1. **La cifra que vale es la media de los cuatro bloques**, no el mejor. En
   cobertura común y parcial, v9 daba `0,364` contra `0,541` en Lugo; si al
   completar sale mejor en un bloque y peor en tres, el veredicto lo dicta la
   media.
2. **Se informa la cobertura de cada barrido junto a cada `F1`.** Si algún
   bloque queda por debajo del `95%`, su cifra se marca como no comparable y
   **no** se promedia en silencio.
3. **El umbral es `0.70`**, el mismo con que están medidos v7 y los demás. No
   se busca el umbral que más favorezca a v9: eso convertiría el bloque en
   validación, que es la regla `15`.
4. **No se toca el precinto.** Nada de esto se evalúa contra los `282` de
   Portugal.
5. **Si v9 pierde, no se propone arreglo en la misma respuesta.** La pregunta
   siguiente —«¿pierde porque la modalidad no sirve o porque se fusiona mal?»—
   tiene un experimento barato preparado y anotado (un bloque
   Squeeze-and-Excitation, `10.1109/cvpr.2018.00745`, menos de `50` parámetros
   con `7` canales) y **eso es otro preregistro**, no una coletilla de este.

## Lo que este experimento NO puede contestar

Aunque v9 gane o pierda limpiamente, sigue sin saberse si la ortofoto ayudaría
**bien fusionada**. v9 concatena; Canedo usa un transformer que aprende cuánto
pesa cada modalidad. Este preregistro mide la concatenación temprana y nada
más, y el veredicto tiene que decirlo con esas palabras — no «la ortofoto no
sirve», sino «concatenar la ortofoto no sirve».
