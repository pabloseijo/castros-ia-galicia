#!/bin/sh
# Los tres bloques que le faltan a v9. Pontevedra ya está: 6.877 filas, F1 0,304.
#
# Preregistro en `docs/preregistros/PREREGISTRO-v9-remedida.md`.
#
# **Los bbox se COPIAN de `barridos_v14.sh`, no se calculan.** Esa regla ya
# existía en este repositorio desde el 2026-08-09 y el 2026-08-10 la salté
# escribiendo un `bbox_de_barrido.py` que los derivaba del propio barrido de v7.
# No funciona, y por una razón que solo se ve midiendo: **el TSV solo contiene
# las celdas que tenían LiDAR** —`7.507` de `8.829` en Pontevedra—, así que su
# mínimo no es el origen de la rejilla sino la celda más occidental CON DATO.
# El resultado fue una rejilla desplazada `101,9 m` de mediana —casi media
# celda— y un fichero de Lugo con dos rejillas mezcladas, archivado en
# `data/descartado/`.
#
# La guarda `verificar_bbox.py` ya existía para esto. Aquí se usa.
set -u
cd "$(dirname "$0")/.." || exit 1
LOG=logs/cadena_v9_completa.log
say() { echo "[$(date +%F\ %H:%M)] $*" | tee -a "$LOG"; }

# **Cola, no desalojo.** Si la GPU la tiene otro trabajo -el 2026-08-10 era un
# entrenamiento de voz de Pablo con la tarjeta en Exclusive_Process- se espera.
esperar_gpu() {
  if ! scripts/gpu_libre.sh; then
    say "GPU ocupada por otro trabajo: esperando"
    until scripts/gpu_libre.sh; do sleep 300; done
    say "GPU libre"
  fi
}

esperar_gpu

if ! .venv-gpu/bin/python scripts/verificar_bbox.py >> "$LOG" 2>&1; then
  say "*** BBOX NO COINCIDE con lo que barrio v7: abortando ***"
  exit 2
fi
say "bbox verificados contra el barrido de v7"

for B in lugo ourense coruna; do
  case "$B" in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
  esac
  OUT="data/sweep_val_${B}_v9.tsv"
  REF="data/sweep_val_${B}_v7.tsv"
  esperar_gpu
  say "=== v9 en $B  bbox=$BB  (ref $(wc -l < "$REF") filas) ==="
  CASTROS_VRAM_FRAC=0.45 scripts/lanzar.sh "barrido-$B-v9" 4000M \
    .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir "data/external/lidar-val-$B" --checkpoint data/cls-v9/best.pt \
    --out "$OUT" --bbox $BB \
    --ortofoto-dir data/ortofotos-rejilla --ortofoto-prefijo "${B}_" \
    --workers 1 --batch 12 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
  say "$B rc=$?  filas=$(wc -l < "$OUT" 2>/dev/null || echo 0) de $(wc -l < "$REF")"

  say "--- evaluacion de $B ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred "$OUT" --truth "data/${B}_fus_truth_limpia.tsv" \
    --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
done

say "=== auditoria de truncados ==="
.venv-gpu/bin/python scripts/auditar_barridos_truncados.py >> "$LOG" 2>&1
say "### cadena v9 terminada ###"
