# Preregistro — v15: la cabeza MIL, que lleva escrita desde el principio y nunca se entrenó

**Escrito el 2026-08-10, antes de entrenar nada y antes de leer el error de
entrenamiento de v7, que está midiéndose mientras se escribe esto.**

## De dónde sale

Ingestados los capítulos 5–9 de Goodfellow, Bengio & Courville, §9.4 dice:

> «La convolución y el *pooling* **pueden causar subajuste**. Si una tarea
> depende de preservar información espacial precisa, aplicar *pooling* a todos
> los rasgos puede **aumentar el error de entrenamiento**.»

Y la cabeza que usan los quince checkpoints de este proyecto es:

```python
return self.fc(F.adaptive_avg_pool2d(x4, 1).flatten(1)), None
```

`512×512 m` → *stride* `32` → mapa de `16×16` (celdas de `32 m`) → **promedio de
las 256 celdas**. Un castro tiene radio mediano `50,8 m` —tres celdas—, así que
el modelo **no puede representar «anillo cerrado de radio `r`»**: solo «cuánta
textura de parapeto hay de media en medio kilómetro».

`train_unet_multiclass.py` ya implementa la alternativa, `--head mil`, y su
propio comentario dice lo mismo que el libro:

> «Log-sum-exp: media suave que tiende al máximo al subir `r`. **Media pura
> diluiría un recinto de `50 m` en una viñeta de `512 m`**; el máximo puro se
> engancha a un píxel de ruido.»

**`--head` tiene `mil` por defecto y las nueve cadenas lo sobrescriben a `cls`.**
La razón escrita era replicar a Landauer et al. (2025), que es un clasificador de
viñetas. Es una razón buena, pero **nadie midió la otra**.

## La hipótesis

**H1**: la cabeza MIL bate a `cls` porque conserva la geometría. El decodificador
emite logits por píxel a `256×256` y el log-sum-exp agrega sin diluir.

**H0**: no la bate. Posibles causas, y las tres son informativas:

- con `773` castros y etiqueta de imagen, el decodificador no tiene supervisión
  suficiente y sobreajusta;
- el log-sum-exp con `r = 8` se comporta como un máximo y se engancha a ruido;
- el cuello no era la geometría.

## Lo que se hace: UN mecanismo, DOS tratamientos

La agregación admite tres formas y el proyecto usa la que más diluye. En vez de
tres preregistros sueltos, esto es **un experimento sobre un mecanismo con dos
tratamientos**, contra el control que ya existe:

| brazo | agregación | estado |
| --- | --- | --- |
| **control** = v7 | media global | medido, `F1 0,512` |
| **v15a** | *log-sum-exp*, `r = 8` (`--head mil`) | implementado, nunca entrenado |
| **v15b** | **atención aprendida** (`--head atencion`) | **implementado el 2026-08-10** |

**Exactamente el mismo corpus, el mismo split, la misma pérdida y las mismas
épocas que v7.** Solo cambia la cabeza.

```sh
.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v7 --out-dir data/cls-v15a \
  --head mil --encoder resnet34 --epochs 16 --batch 16 --workers 2 \
  --loss focal --focal-gamma 2.0

.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v7 --out-dir data/cls-v15b \
  --head atencion --encoder resnet34 --epochs 16 --batch 16 --workers 2 \
  --loss focal --focal-gamma 2.0
```

`--batch 16` puede no caber con el decodificador de `mil`; si hay que bajarlo,
**se declara aquí y no se toca nada más**. La atención cuesta `21,35 M`
parámetros contra `21,29 M` de `cls` — comprobado, no estimado— así que ahí no
hay problema de memoria.

### Por qué la atención y no solo el log-sum-exp

Ilse, Tomczak y Welling (ICML 2018, `arXiv:1802.04712`, `2.734` citas) proponen
un operador de agregación **invariante a permutaciones** que aprende el peso de
cada instancia. Es **estrictamente más expresivo** que la media y que el
log-sum-exp: puede aprender a comportarse como cualquiera de las dos. Y el
encaje no es analógico — una viñeta con etiqueta de imagen y sin máscaras **es**
una bolsa de instancias con una sola etiqueta, que es el problema que ese
artículo define. Detalle en
[[agregacion-espacial-tres-formas-de-no-diluir-el-objeto]].

**Si v15b no bate a v7, la vía de la agregación queda cerrada**, porque el brazo
más expresivo de los tres habrá fallado.

## El listón, que es el de siempre

> **`F1 ≥ 0,542` de media en los cuatro bloques** —`+0,03` sobre el `0,512` de
> v7— **y recall de castro `≥ 0,70`.** No se mueve.

Y la condición añadida el `2026-08-09`: si gana, comprobar con
`conjunto_no_pierde.py` que **no pierde castros que el conjunto congelado sí
encontraba**.

## Lo que se declara de antemano

1. **Se mide el error de ENTRENAMIENTO además del de validación**, con
   `error_de_entrenamiento.py`. Es la carencia que este proyecto arrastra en sus
   quince checkpoints, y la predicción de este preregistro es concreta: si la
   cabeza `cls` subajusta por colapso espacial, **v15 debe bajar el error de
   entrenamiento**, gane o no en validación. Esa es la prueba del mecanismo,
   separada de la prueba del resultado.
2. **El mapa de calor es un subproducto, no una métrica.** Que se vean bonitos
   los recintos en QGIS no es evidencia de nada.
3. **Cuatro bloques o ninguno.** Nada de parar en Lugo y extrapolar.
4. **Cobertura al lado de cada `F1`.** La lección del `2026-08-10`: un barrido al
   `44%` produjo el veredicto de v9 y no medía a v9.
5. **No se toca el precinto de Portugal.**

## Lo que este experimento NO contesta

Si v15 pierde, no queda demostrado que la geometría no importe: quedaría
demostrado que **esta forma** de conservarla —decodificador U-Net supervisado por
etiqueta de imagen con log-sum-exp— no funciona con `773` positivos. La otra vía
sin reentrenar la red sería el **prototipo espacial** del TFG de los pingüinos,
que fue su mayor ganancia en la etapa análoga, y es otro preregistro.
