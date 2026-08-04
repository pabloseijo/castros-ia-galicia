# Arranque en la máquina con GPU

Todo lo que precede a la red está hecho y medido. Esto es lo único que falta
cuando la GPU esté conectada (Ubuntu server + Tailscale, igual que la Pi).

## 1. Entorno

```bash
python3 -m venv .venv-gpu && . .venv-gpu/bin/activate
pip install torch torchvision timm scikit-learn numpy   # CUDA según tu tarjeta
pip install segmentation_models_pytorch                  # solo si vas a segmentar
```

## 2. Traer el corpus desde la Raspberry

El caché de viñetas es lo único necesario para entrenar; pesa poco al lado de
los LAZ, que se quedan en la Pi.

```bash
rsync -avz admin@raspberri:/srv/data/castros-ia-galicia-current/data/galicia-vignettes-v2/ \
  data/galicia-vignettes-v2/          # 8.741 viñetas, ~8.5 GB
rsync -avz admin@raspberri:/srv/data/castros-ia-galicia-current/data/cpu-baseline-multiclass-v1/ \
  data/cpu-baseline-multiclass-v1/    # la línea base a batir
```

## 3. Entrenar la U-Net multiclase

```bash
python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v2 \
  --out-dir data/unet-multiclass-v1 \
  --encoder resnet34 --epochs 40
```

**El único criterio de éxito**: batir la línea base de CPU con holgura.

| clase | línea base CPU (recall) | la U-Net tiene que superar |
|---|---:|---|
| castro | `0.72` | claramente, o no compensa |
| mámoa | `0.36` | ídem; si colapsa a `0`, volver a binario |

El script reporta por clase y marca `COLAPSADA` cualquier clase con recall `0`.
Selecciona el modelo por la media de recall de castro y mámoa, no por accuracy
global —que la clase fondo domina.

## 4. Después de la red

1. `python scripts/evaluate_cascade.py` con los scores de la U-Net: mide la
   ganancia de la criba sobre el modelo real, no sobre la línea base.
2. Bucle de *hard negative mining* (la palanca de Canedo, `5.678 → 40`): correr
   sobre terreno no catalogado, revisar los falsos positivos en QGIS, añadirlos
   como negativos, reentrenar.
3. Máscaras vía SAM auto-prompteado sobre los polígonos OSM, para pasar de
   clasificación a segmentación densa.

## Orden de prioridad, por si el tiempo aprieta

La arquitectura da `1.4` puntos (U-Net vs Swin). La criba da `+3.3` pp de VPP.
La minería llevó a Canedo de `0.26` a F1 `0.66`. **Invierte en la minería antes
que en la arquitectura.**
