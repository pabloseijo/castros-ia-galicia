# Preregistro — v17: entrenar más, porque se cortó mientras aún mejoraba

**Escrito el 2026-08-10, antes de entrenar.**

## La evidencia, que es de nuestra propia curva

El `2026-08-10` se midió por primera vez el error de entrenamiento de v7:
**recall de castro `0,710` sobre los datos que vio y `0,711` sobre los que no.
Brecha: una milésima.** Es subajuste puro y cero sobreajuste
([[subajuste-puro-la-brecha-es-cero]]).

Ante subajuste, el libro (§5.2) da tres salidas: **más capacidad**, **mejor
representación** y **menos regularización**. Hay una cuarta, más barata, y la
curva de v7 la señala:

| época | pérdida | `F1` castro | recall castro |
| ---: | ---: | ---: | ---: |
| `9` | `0,2181` | `0,5517` | `0,711` |
| `13` | `0,1636` | `0,5468` | `0,828` |
| `15` | `0,1284` | `0,5525` | `0,833` |
| **`16`** | `0,1332` | **`0,5640`** | **`0,844`** |

**La pérdida bajaba monótona y el `F1` de castro seguía subiendo en la última
época.** El entrenamiento no se detuvo porque hubiera convergido: se detuvo
porque `--epochs 16` con `CosineAnnealingLR(T_max=16)` lleva la tasa de
aprendizaje a cero justo ahí.

> **Se cortó mientras aún mejoraba.**

## La hipótesis

**H1**: con `40` épocas el modelo sigue bajando el error de entrenamiento y sube
el `F1` de castro. Es lo que predice el diagnóstico de subajuste.

**H0**: no mejora, o mejora el entrenamiento y no la validación. Lo segundo
sería la primera evidencia de **sobreajuste** en este proyecto, y cambiaría el
diagnóstico: querría decir que el subajuste medido era el suelo de Bayes y no
falta de ajuste.

## Lo que se hace

Exactamente la configuración de v7 con `--epochs 40`. **Un solo cambio.** El
planificador coseno se estira solo, porque su `T_max` es `args.epochs`.

```sh
.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v7 --out-dir data/cls-v17 \
  --head cls --encoder resnet34 --epochs 40 --batch 16 --workers 2 \
  --loss focal --focal-gamma 2.0
```

## El listón, que no se mueve

> **`F1 ≥ 0,542` de media en los cuatro bloques y recall de castro `≥ 0,70`.**

## Lo que se declara de antemano

1. **Se mide el error de entrenamiento al final**, con
   `error_de_entrenamiento.py`. Es la prueba del mecanismo: si `40` épocas no
   bajan el error de entrenamiento por debajo del `0,710` de recall de v7, el
   problema **no era la duración**.
2. **Se guarda `best_castro.pt`** además de `best.pt`, y se declara aquí cuál se
   usa para barrer: **`best_castro.pt`**, por lo medido en
   `PREREGISTRO-checkpoint-por-castro.md`.
3. **Cobertura al lado de cada `F1`.**
4. **No se toca el precinto.**

## Por qué esto va después de v15 y no antes

v15 prueba **la representación** (cómo se agregan las `256` celdas) y v17 prueba
**la duración**. Si v15 arregla el subajuste, v17 sobra; si no lo arregla, v17
dice si el cuello era simplemente que no se entrenó bastante. **El orden importa
porque el segundo resultado se interpreta a la luz del primero**, y hacerlos a la
vez sobre la misma GPU de `8 GB` no cabe.
