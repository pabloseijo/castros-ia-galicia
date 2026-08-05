# La tubería viva

De los `86` scripts del repo, **estos diez son los que están en uso**. El resto es
historial: exploraciones, hipótesis refutadas y ramas superadas. No están
borrados porque documentan por qué el proyecto es como es, pero **no hace falta
leerlos para ejecutarlo**.

Escrito el `2026-08-05` porque `41` de los `86` no aparecían citados en ninguna
parte —ni en la wiki, ni en el `Makefile`, ni importados— y entre ellos estaba
`design_terrain_cascade.py`, que produce la criba que multiplica el VPP por
`2,79`. El problema no era que sobrara código: era que no había forma de saber
cuál importaba.

## El camino, en orden

| paso | script | qué hace |
|---|---|---|
| 1 | `download_positive_centred_lidar.py` | baja teselas LiDAR PNOA a `1 m` |
| 2 | `build_trasancos_hard_negatives.py` | negativos con nombre desde OSM |
| 3 | `sample_terrain_negatives.py` | fondo de terreno aleatorio |
| 4 | `build_trasancos_vignettes.py` | corta viñetas de relieve, 3 canales |
| 5 | `spatial_thinning.py` | diluido espacial de positivos (opcional) |
| 6 | `train_unet_multiclass.py` | entrena; `--head cls` es el que gana |
| 7 | `eval_checkpoint.py` | evalúa un checkpoint sin reentrenar |
| 8 | `sweep_grid_lidar.py` | barrido ciego con paso de media ventana |
| 9 | `detection_eval.py` | F1 por yacimiento y VPP a tasa real |
| — | `honest_eval.py` | biblioteca: Wilson, VPP, NNS. La usan casi todos |

Auxiliares que siguen vivos: `bench_gpu.py` (medir antes de optimizar),
`lit_search.py` (literatura con control de calidad dentro),
`design_terrain_cascade.py` (la criba, `x2.79` de VPP),
`train_cpu_baseline.py` (el suelo que la red tuvo que batir).

## Cómo se ejecuta hoy

Todo corre en `oval-server`, que tiene el LiDAR en disco local y la GPU:

```bash
# corpus -> entrenamiento, encadenado y desacoplado
nohup setsid ./cadena_v3.sh > logs/cadena-v3.log 2>&1 < /dev/null &
# entrenamiento -> barrido -> evaluación
nohup setsid ./cadena_barrido.sh > logs/cadena-barrido.log 2>&1 < /dev/null &
```

Detalles de la máquina y sus trampas —AMP no acelera en Pascal,
`channels_last` es `5,4x` más lento— en `ops/GPU_ARRANQUE.md`.

## Lo que no se debe repetir

Está todo en la wiki, en `wiki/vida/carrera/arqueologia-computacional/`, pero en
corto: no ordenar literatura por citas, no seleccionar modelo por media de
recall, no usar `channels_last` en esta GPU, no fiarse del AUC para detectar
sesgo de muestreo, y no declarar bloqueado un PDF sin haberlo intentado con
navegador real.
