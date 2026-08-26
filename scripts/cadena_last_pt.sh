#!/bin/sh
# ¿La métrica de selección congeló el checkpoint equivocado?
# Preregistro en `docs/preregistros/PREREGISTRO-checkpoint-por-castro.md`, escrito ANTES de esto.
#
# `best.pt` de v7 es la época 9 (F1 castro 0,5518, recall 0,711).
# `last.pt` es la 16 y es la MEJOR en castro de las dieciséis
# (F1 0,5640, recall 0,844). Se descartó porque su F1 de mámoa era 0,035
# peor, y la mámoa tiene n=122 con precisión 0,21-0,24: la clase más ruidosa
# del corpus eligiendo el modelo.
#
# No hay que entrenar nada: `last.pt` ya está en disco.
#
# Espera a que termine la cadena de v15, que usa la GPU entera.
set -u
cd "$(dirname "$0")/.." || exit 1
LOG=logs/cadena_last_pt.log
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

for B in lugo ourense coruna pontevedra; do
  OUT="data/sweep_val_${B}_v7last.tsv"
  REF="data/sweep_val_${B}_v7.tsv"
  case "$B" in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
  esac

  esperar_gpu
  say "=== v7-last en $B  bbox=$BB ==="
  con_gpu 43200 scripts/lanzar.sh "barrido-$B-v7last" 4000M \
    .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir "data/external/lidar-val-$B" --checkpoint data/cls-v7/last.pt \
    --out "$OUT" --bbox $BB \
    --workers 2 --batch 24 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
  say "$B rc=$?  filas=$(wc -l < "$OUT" 2>/dev/null || echo 0) de $(wc -l < "$REF")"

  say "--- v7-last en $B ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred "$OUT" --truth "data/${B}_fus_truth_limpia.tsv" \
    --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
  say "--- v7-best en $B (referencia) ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred "$REF" --truth "data/${B}_fus_truth_limpia.tsv" \
    --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
done

say "=== F1 con cobertura de todo lo que hay ==="
.venv-gpu/bin/python scripts/f1_con_cobertura.py >> "$LOG" 2>&1
say "### cadena last.pt terminada ###"
