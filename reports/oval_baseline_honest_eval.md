# Evaluación honesta

`49` muestras: `7` positivos, `42` negativos.

| magnitud | valor |
|---|---:|
| ratio neg:pos observado | `1:6` |
| ratio neg:pos en barrido real | `1:474` |
| **desajuste** | **`79.0x`** |
| ROC-AUC | `0.8129` IC95% `[0.596, 0.976]` |
| average precision | `0.5698` IC95% `[0.169, 0.881]` |

## Por profundidad de cola

| K | precisión | IC95% | **a tasa base real** | recall | horas de revisión |
|---:|---:|---|---:|---:|---:|
| 10 | `0.40` | `[0.17, 0.69]` | **`0.01`** | `0.57` | `0.2 h` |
| 25 | `0.24` | `[0.11, 0.43]` | **`0.00`** | `0.86` | `0.3 h` |

## Qué puede resolver este conjunto

Anchura del IC95% al estimar un recall de `0.70`: **`0.56`**.

> **No distingue un recall de `0.70` de uno de `0.60`.** Cualquier
> mejora menor que esa anchura es indistinguible del ruido de muestreo.
> Harían falta del orden de `300` positivos.

La columna «a tasa base real» reexpresa la precisión al ratio del barrido
(`1:474`), que es lo que vería quien abra la cola en QGIS. La precisión
medida sobre la mezcla de validación es optimista por construcción.
