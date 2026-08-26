# Preregistro: el canal de apertura desplaza el punto de operación

**Escrito el 2026-08-08 a las 05:50, con tres bloques de v8 medidos y Pontevedra
todavía barriéndose.** Se escribe ahora, antes de cerrar el cuarto, para que
quede fechado **antes** del veredicto de `PREREGISTRO-v8.md` y no pueda leerse
como una excusa fabricada después de perder.

## Lo que se ha visto, y lo que NO se va a hacer con ello

v8 —v7 más el canal de apertura— pierde contra su listón en umbral `0.70`:

| bloque | precisión v7 → v8 | F1 v7 → v8 |
|---|---|---|
| Lugo | `0.826` → `0.547` | `0.697` → `0.631` |
| A Coruña | `0.769` → `0.380` | `0.396` → `0.419` |
| Ourense | `0.543` → `0.302` | `0.535` → `0.439` |

El efecto es **sistemático y en la misma dirección en los tres**: el recall sube
mucho —en Ourense de `~0.53` a `0.806`— y la precisión se hunde. El canal no
empeora el modelo: **lo hace más permisivo**.

Y de ahí sale la observación incómoda. Los mejores `F1` de v8 caen todos en
umbral `0.80`, no en `0.70`: Lugo `0.655`, A Coruña `0.419`, Ourense `0.579`.
Media de los tres: **`0.551`**, por encima del listón de `0.542`.

**Eso no rescata a v8.** `PREREGISTRO-v8.md` fijó umbral `0.70` antes de existir
ningún número, y cambiarlo ahora, con los resultados delante, es la definición
de mover la portería. Un listón que se ajusta cuando no se cumple no es un
listón. **v8 queda refutado tal y como se preregistró**, en cuanto Pontevedra
confirme la media.

## La hipótesis nueva, que es otra cosa

> **El canal de apertura mejora el `F1` cuando el umbral acompaña al punto de
> operación que induce.**

Es una afirmación distinta de la que se probó, y por eso necesita su propia
medición limpia. No se puede contestar con estos datos: el umbral `0.80` se
eligió **mirando** estos resultados, así que cualquier cifra suya está sesgada
por selección.

## Cómo se contestaría bien

1. **El umbral se elige en validación, no en el banco de evaluación.** Barrer un
   bloque distinto —o el conjunto `val` del corpus— y sacar de ahí el umbral
   óptimo de v8 y el de v7, cada uno el suyo.
2. **Comparar a umbral propio**, no a umbral común: si el canal desplaza el punto
   de operación, obligar a los dos modelos al mismo umbral mide el desplazamiento
   y no la calidad.
3. **El listón sigue siendo `+0.03`** sobre la media de v7 medida a *su* mejor
   umbral, no a `0.70`. Comparar el mejor de uno contra un punto arbitrario del
   otro es la trampa inversa.
4. Y una pregunta que la aritmética no contesta: **¿compensa?** El canal
   multiplica por `~4` el coste del barrido —de `~40 min` a `~2,5 h` por bloque,
   medido esta noche— y para barrer Galicia entera eso pesa.

## Lo que hay que recordar al leer esto

Un experimento puede fallar su listón **y** haber enseñado algo. Lo que no se
puede es cobrar lo segundo como si fuera lo primero. El resultado de esta noche
es: **el canal de apertura, tal y como se preregistró, no pasa**. Lo demás es una
línea de trabajo, no un resultado.
