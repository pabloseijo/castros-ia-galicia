#!/bin/bash
# v6-focal = mismo corpus v6 (534 negativos duros de OSM), pero con Focal Loss
# (Lin et al. 2017) en vez de CrossEntropyLoss balanceado por clase.
#
# Diagnóstico del 2026-08-06: con `balanced`, los 534 negativos duros son el
# 4,9% de las viñetas de "fondo" y se llevan ~1,6% del gradiente total. 16 de
# 26 falsos positivos de Pontevedra resultaron estar a 1 m de un sitio visto
# así en entrenamiento y el modelo lo seguía puntuando 0.82-0.99. No se mina
# nada nuevo: es el mismo corpus, solo cambia cómo se pesa cada ejemplo.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v6_focal.log
mkdir -p logs
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

say "=== esperando a que la GPU quede libre ==="
while pgrep -f "train_unet_multiclass.py|sweep_grid_lidar.py" > /dev/null 2>&1; do sleep 60; done
sleep 5
say "GPU libre: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"

say "=== entrenando v6-focal (mismo corpus v6, focal loss gamma=2.0) ==="
.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v6 --out-dir data/cls-v6-focal \
  --head cls --encoder resnet34 --epochs 16 --batch 16 --workers 4 \
  --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
RC=$?
say "entrenamiento rc=$RC"
if [ "$RC" -ne 0 ]; then
  say "*** ENTRENAMIENTO FALLÓ (rc=$RC): abortando cadena, no se barre ni se evalúa ***"
  exit "$RC"
fi

say "=== barriendo y evaluando ==="
for B in lugo pontevedra; do
  case $B in
    lugo) BB="-7.375 42.625 -7.125 42.875";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
  esac
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-val-$B --checkpoint data/cls-v6-focal/best.pt \
    --out data/sweep_val_${B}_v6focal.tsv --bbox $BB --workers 2 --batch 16 >> "$LOG" 2>&1
  RC=$?
  say "barrido $B rc=$RC"
  if [ "$RC" -ne 0 ]; then
    say "*** BARRIDO $B FALLÓ (rc=$RC): no se evalúa esta cifra ***"
    continue
  fi
  say "--- $B con v6-focal ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_val_${B}_v6focal.tsv --truth data/${B}_truth_limpia.tsv \
    --mascara data/${B}_mascara_train.tsv --umbrales 0.5 0.7 0.8 0.9 >> "$LOG" 2>&1
done
say "referencia v3:       Lugo prec 0.808 F1 0.743 | Pontevedra prec 0.179 F1 0.274"
say "referencia v6 (534 negativos, sin focal): Lugo prec 0.717 F1 0.667 | Pontevedra prec 0.235-0.267 F1 0.254"
say "=== cadena v6-focal completa ==="
