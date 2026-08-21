# Preregistro — v16: la ventana de 256 m, porque la de 512 se eligió con el número equivocado

**Escrito el 2026-08-10, antes de construir el corpus y antes de leer el error
de entrenamiento de v7.**

## El error de diseño, con número

`build_trasancos_vignettes.py`, línea 63:

```python
EXTENT_M = 512.0      # vignette side; a 114 m castro fills ~22% of the frame
```

`114 / 512 = 22%` es la fracción **lineal**. Pero lo que promedia un *global
average pooling* son **celdas**, o sea **área**:

```text
π·(114/2)² / 512²  =  3,89%
```

**El comentario que justifica la ventana está calculado sobre la magnitud
equivocada, y se equivoca por un factor de `5,7×`.**

Con el radio mediano medido el `2026-08-10` sobre `211` castros —`50,8 m`, o sea
`102 m` de diámetro— la cuenta real es:

| ventana | fracción lineal | **fracción de área** | celdas del mapa |
| ---: | ---: | ---: | --- |
| **`512 m`** (actual) | `19,9%` | **`3,1%`** | `8` de `256` |
| `384 m` | `26,6%` | `5,5%` | `8` de `144` |
| **`256 m`** | `39,8%` | **`12,5%`** | `8` de `64` |

> El promedio global atenúa la evidencia del castro **`32×`** con la ventana
> actual y **`8×`** con una de `256 m`.

## La hipótesis

**H1**: con ventana de `256 m` el modelo mejora, porque la dilución baja `4×`.
Es el mismo mecanismo que ataca [[PREREGISTRO-v15-cabeza-mil]] por el otro
extremo: v15 cambia **cómo se agrega**, v16 cambia **cuánto hay que agregar**.

**H0**: no mejora. Y entonces —si tampoco mejora v15— **el mecanismo de la
dilución está refutado**, que es un resultado limpio: dos ataques
independientes al mismo cuello, los dos fallidos.

## Lo que cuesta, que es lo que hace esto viable

Parecía caro y no lo es. Con solape del `50%`:

| | ventana `512 m` | ventana `256 m` |
| --- | ---: | ---: |
| paso | `256 m` | `128 m` |
| ventanas por bloque | `~8.600` | `~34.400` (`4×`) |
| píxeles por ventana | `512²` | `256²` (`4×` menos) |
| **coste total de GPU** | `1×` | **`~1×`** |

La descompresión de LAZ —que es el `87,6%` del coste del barrido— **no cambia**:
se cubre la misma superficie. El barrido total de Galicia sigue en las mismas
`~134` horas del roadmap.

## Lo que se hace

1. Reconstruir el corpus con `--extent-m 256`, **mismos positivos, mismo split
   espacial, misma proporción**. Un solo cambio.
2. Entrenar con la configuración exacta de v7: `--head cls`, `resnet34`,
   `16` épocas, focal `gamma 2.0`. **No se mezcla con v15.**
3. Barrer los cuatro bloques con `--extent-m 256` y paso `128 m`.

## El listón, que es el de siempre

> **`F1 ≥ 0,542` de media en los cuatro bloques y recall de castro `≥ 0,70`.**

Y la condición del `2026-08-09`: si gana, comprobar que no pierde castros que el
conjunto congelado sí encontraba.

## Lo que se declara de antemano

1. **Se mide el error de entrenamiento**, igual que en v15. La predicción del
   mecanismo es que **baje**; si el `F1` sube pero el error de entrenamiento no
   baja, la mejora no viene de donde dice esta hipótesis y hay que decirlo.
2. **La comparación es a igualdad de superficie barrida, no de número de
   ventanas.** Cuatro veces más ventanas producen cuatro veces más detecciones
   brutas; lo que se compara es castros hallados por ficha, como siempre.
3. **Un castro grande no cabe holgado.** Los radios van de `38` a `83 m`
   (p10–p90), así que un castro de `166 m` de diámetro deja `45 m` de margen en
   una ventana de `256 m`. **Es una limitación real y se declara aquí**: si v16
   pierde recall precisamente en los castros grandes, esa es la causa y se
   comprueba mirando el recall por cuartil de radio, no por impresión.
4. **No se toca el precinto.**

## Lo que este experimento NO contesta

Si v16 gana, no queda claro si es por la dilución o simplemente porque un objeto
mayor en píxeles relativos es más fácil. Separarlo exigiría una tercera
condición —ventana `256 m` con la cabeza MIL— y **eso no está en esta lista**:
la lista es de dos, y se cierra.
