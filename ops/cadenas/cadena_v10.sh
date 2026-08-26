#!/bin/bash
# v10 = v7 con los falsos positivos del barrido minados Y CON PESO.
# Ver `docs/preregistros/PREREGISTRO-v10.md`. Liston: F1 medio >= 0.542.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v10.log
say() { echo "[$(date +%H:%M)] $*" | tee -a "$LOG"; }
B4="lugo coruna ourense pontevedra"
bbox() { case $1 in
  lugo) echo "-7.375 42.625 -7.125 42.875";;
  pontevedra) echo "-8.875 42.125 -8.625 42.375";;
  coruna) echo "-8.50 43.00 -8.25 43.25";;
  ourense) echo "-8.25 42.25 -8.00 42.50";; esac; }

say "### v10: mineria de falsos positivos CON PESO ###"
say "=== esperando a que v9 suelte la GPU ==="
while pgrep -f "train_unet[_]multiclass.py|sweep_grid[_]lidar.py" >/dev/null 2>&1; do sleep 120; done
sleep 20

say "=== 1. extrayendo falsos positivos de los cuatro barridos de v7 ==="
FPARGS=""
for B in $B4; do
  .venv-gpu/bin/python scripts/extraer_fp_barrido.py \
    --pred data/sweep_val_${B}_v7.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv --umbral 0.5 \
    --out data/fp_${B}.tsv >> "$LOG" 2>&1
  N=$(( $(wc -l < data/fp_${B}.tsv) - 1 ))
  say "  $B: $N falsos positivos"
  FPARGS="$FPARGS data/fp_${B}.tsv:data/external/lidar-val-$B"
done

say "=== 2. cortando las vinnetas de los negativos minados ==="
.venv-gpu/bin/python scripts/minar_negativos_duros.py \
  --fp $FPARGS --corpus data/galicia-vignettes-v7 \
  --salida data/galicia-vignettes-v10 \
  --grupo hard_negative_barrido --workers 3 >> "$LOG" 2>&1
say "corte rc=$?"
N=$(( $(wc -l < data/galicia-vignettes-v10/index.tsv 2>/dev/null || echo 1) - 1 ))
say "corpus v10: $N vinnetas (v7 tiene 15311)"
[ "$N" -lt 15000 ] && { say "*** corpus corto: abortando ***"; exit 1; }
say "  negativos duros totales:"
awk -F"\t" 'NR>1 && $3 ~ /^hard_negative/ {n++} END{print "    "n+0}' \
  data/galicia-vignettes-v10/index.tsv | tee -a "$LOG"

say "=== 3. entrenando v10 (peso 8 a los negativos duros) ==="
.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v10 --out-dir data/cls-v10 \
  --head cls --encoder resnet34 --epochs 16 --batch 16 --workers 4 \
  --loss focal --focal-gamma 2.0 --peso-negativo-duro 8 >> "$LOG" 2>&1
RC=$?; say "entrenamiento rc=$RC"
[ "$RC" -ne 0 ] && { say "*** ENTRENAMIENTO v10 FALLO ***"; exit "$RC"; }

say "=== 4. barriendo y evaluando ==="
for B in $B4; do
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-val-$B --checkpoint data/cls-v10/best.pt \
    --out data/sweep_val_${B}_v10.tsv --bbox $(bbox $B) \
    --workers 2 --batch 16 --chunk 100 --max-celdas-tarea 30 >> "$LOG" 2>&1
  say "barrido $B rc=$?"
  say "=== EVALUACION $B con v10, metro fusionado ==="
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_val_${B}_v10.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv --umbrales 0.5 0.7 0.8 0.9 >> "$LOG" 2>&1
  .venv-gpu/bin/python scripts/extraer_candidatos.py \
    --pred data/sweep_val_${B}_v10.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv --umbral 0.7 \
    --out data/candidatos_${B}_v10.tsv >> "$LOG" 2>&1
done
say "=== referencia v7: F1 medio 0.512 | liston 0.542 ==="
say "### v10 completa ###"
