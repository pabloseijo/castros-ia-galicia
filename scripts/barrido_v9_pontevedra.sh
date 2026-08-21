#!/bin/sh
# v9 (ortofoto como canal) en Pontevedra: la pregunta que su propio preregistro
# dejo abierta por escrito y nadie contesto.
#
# v9 se refuto con UN bloque —Lugo, `F1 0,222` contra `0,697`— y la desviacion
# quedo declarada. Pero el documento dice literalmente: «no se sabra si v9 se
# comporta distinto en Pontevedra, que es donde la ortofoto debia ayudar mas
# (precision `0,391`, confusor periurbano). Esa pregunta queda abierta, y si
# algun dia se retoma la via espectral hay que empezar por ahi, no por Lugo».
#
# **El bbox NO se copia de `cola_barridos_v9.sh`.** Ese guion tiene
# `-8.75 42.25 -8.50 42.50` para Pontevedra, que es OTRO SITIO: el bueno es
# `-8.875 42.125 -8.625 42.375`. Es el mismo fallo que el 2026-08-09 hizo barrer
# un trozo distinto de Galicia durante horas con cifras que parecian validas.
# Nunca llego a ejecutarse, asi que el error estaba latente.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/barrido_v9_pontevedra.log
say() { echo "[$(date +%F' '%H:%M)] $*" >> "$LOG"; }

say "### v9 en Pontevedra: la pregunta abierta del preregistro ###"

if ! .venv-gpu/bin/python scripts/verificar_bbox.py >> "$LOG" 2>&1; then
  say "*** BBOX NO COINCIDE con lo que barrio v7: abortando ***"
  exit 2
fi
say "bbox verificados contra el barrido de v7"

B=pontevedra
OUT="data/sweep_val_${B}_v9.tsv"
REF="data/sweep_val_${B}_v7.tsv"
rm -f "$OUT"

say "=== barrido $B con v9 (7 canales, con ortofoto) ==="
CASTROS_VRAM_FRAC=0.45 scripts/lanzar.sh "barrido-$B-v9" 6000M \
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
  --laz-dir "data/external/lidar-val-$B" --checkpoint data/cls-v9/best.pt \
  --out "$OUT" --bbox -8.875 42.125 -8.625 42.375 \
  --ortofoto-dir data/ortofotos-rejilla --ortofoto-prefijo "${B}_" \
  --workers 1 --batch 12 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
say "barrido rc=$?  filas=$(wc -l < "$OUT" 2>/dev/null || echo 0) (v7: $(wc -l < "$REF"))"

.venv-gpu/bin/python scripts/detection_eval.py \
  --pred "$OUT" --truth "data/${B}_fus_truth_limpia.tsv" \
  --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
say "### terminado ###"
