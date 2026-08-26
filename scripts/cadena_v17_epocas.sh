#!/bin/sh
# v17: la misma configuración de v7 con 40 épocas en vez de 16.
# Preregistro en `docs/preregistros/PREREGISTRO-v17-mas-epocas.md`, escrito ANTES de esto.
#
# La curva de v7 se cortó mientras aún mejoraba: F1 de castro 0,5517 en la
# época 9 y 0,5640 en la 16, con la pérdida bajando monótona. No convergió:
# `CosineAnnealingLR(T_max=16)` llevó la tasa a cero justo ahí.
#
# Va el último de la cola porque su resultado se interpreta a la luz de v15:
# v15 prueba la representación, v17 prueba la duración.
set -u
cd "$(dirname "$0")/.." || exit 1
LOG=logs/cadena_v17.log
say() { echo "[$(date +%F\ %H:%M)] $*" | tee -a "$LOG"; }

say "sin espera encadenada: el cerrojo de GPU serializa"

# **Cola, no desalojo.** Si la GPU la tiene otro trabajo -el 2026-08-10 era un
# entrenamiento de voz de Pablo con la tarjeta en Exclusive_Process- se espera.
# **Cerrojo, no cadena de marcadores.** Antes cada cadena esperaba a que la
# anterior escribiera "terminada" en su log. Eso encadenaba tres esperas SIN
# PLAZO: si v9 no llegaba a completarse, v15 esperaba para siempre y arrastraba
# a last_pt y a v17. Un punto único de fallo para toda la cola.
#
# Y era innecesario: v15 entrena sobre el corpus de v7 y **no depende de v9
# para nada**; esperaba solo para no competir por la GPU. Eso es exactamente
# para lo que sirve un cerrojo.
#
# `flock` serializa de verdad —el que no lo tiene, espera— y con `-w` se puede
# poner plazo, así que ninguna cadena puede quedarse colgada de otra.
GPU_LOCK=data/gpu.lock
: > "$GPU_LOCK" 2>/dev/null || true
con_gpu() {   # con_gpu <segundos de plazo> <orden...>
  PLAZO=$1; shift
  flock -w "$PLAZO" 9 || { say "no consegui el cerrojo de GPU en ${PLAZO}s: sigo igual"; }
  "$@"
} 9>>"$GPU_LOCK"

esperar_gpu() {
  if ! scripts/gpu_libre.sh; then
    say "GPU ocupada por otro trabajo: esperando"
    until scripts/gpu_libre.sh; do sleep 300; done
    say "GPU libre"
  fi
}

esperar_gpu

con_gpu 43200 env CASTROS_VRAM_FRAC=0.85 .venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v7 --out-dir data/cls-v17 \
  --head cls --encoder resnet34 --epochs 40 --batch 16 --workers 2 \
  --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
say "entrenamiento v17 rc=$?"
[ -f data/cls-v17/best.pt ] || { say "*** sin checkpoint ***"; exit 1; }

# La prueba del mecanismo, separada de la del resultado.
say "--- error de entrenamiento de v17 ---"
.venv-gpu/bin/python scripts/error_de_entrenamiento.py \
  --modelo v17 --vig data/galicia-vignettes-v7 --batch 16 >> "$LOG" 2>&1

# Se barre con `best_castro.pt`, declarado en el preregistro.
CK=data/cls-v17/best_castro.pt
[ -f "$CK" ] || CK=data/cls-v17/best.pt
say "barriendo con $CK"
for B in lugo ourense coruna pontevedra; do
  OUT="data/sweep_val_${B}_v17.tsv"
  REF="data/sweep_val_${B}_v7.tsv"
  case "$B" in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
  esac
  esperar_gpu
  say "=== v17 en $B ==="
  con_gpu 43200 scripts/lanzar.sh "barrido-$B-v17" 4000M \
    .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir "data/external/lidar-val-$B" --checkpoint "$CK" \
    --out "$OUT" --bbox $BB \
    --workers 2 --batch 24 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
  say "$B rc=$?  filas=$(wc -l < "$OUT" 2>/dev/null || echo 0) de $(wc -l < "$REF")"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred "$OUT" --truth "data/${B}_fus_truth_limpia.tsv" \
    --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
done

say "=== resumen con cobertura ==="
.venv-gpu/bin/python scripts/f1_con_cobertura.py >> "$LOG" 2>&1
say "### cadena v17 terminada ###"
