#!/bin/bash
# v11 = el modelo con TODOS los positivos disponibles, no el 25%.
#
# El cuello no era la arquitectura. Con 3.781 castros catalogados en Galicia,
# el corpus solo tiene 960 con vinneta (25%) y 773 en entrenamiento, porque el
# resto no tenia LiDAR descargado. Cinco versiones peleando por +-0.03 de F1
# sobre 773 positivos, cuando el dato para triplicarlos estaba a una descarga.
#
# Esto no es "otra version": es otro conjunto de entrenamiento. Por eso no lleva
# el liston de +0.03 de los experimentos de arquitectura — se compara con v7 y se
# reporta el cambio, sea el que sea.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v11.log
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

say "### v11: corpus con todos los positivos ###"
say "=== esperando a que termine la descarga de LiDAR ==="
while pgrep -f "download_positive[_]centred_lidar.py" >/dev/null 2>&1; do sleep 300; done
say "descarga terminada: $(ls data/external/lidar-positives-v1/*.laz 2>/dev/null | wc -l) teselas"

say "=== esperando a que la GPU quede libre (v9 y v10) ==="
while pgrep -f "train_unet[_]multiclass.py|sweep_grid[_]lidar.py" >/dev/null 2>&1; do sleep 180; done
sleep 30

say "=== 1. construyendo el corpus completo ==="
.venv-gpu/bin/python scripts/build_trasancos_vignettes.py \
  --laz-dir data/external/lidar-positives-v1 data/external/lidar-trasancos-v1 \
            data/external/lidar-val-lugo data/external/lidar-val-pontevedra \
            data/external/lidar-val-coruna data/external/lidar-val-ourense \
  --out-dir data/galicia-vignettes-v11 --scope galicia \
  --extra-negatives data/negativos_puntuados_v3.tsv \
  --workers 3 >> "$LOG" 2>&1
say "corpus rc=$?"
N=$(( $(wc -l < data/galicia-vignettes-v11/index.tsv 2>/dev/null || echo 1) - 1 ))
NC=$(awk -F"\t" 'NR>1 && $3=="castro"' data/galicia-vignettes-v11/index.tsv 2>/dev/null | wc -l)
say "corpus v11: $N vinnetas, $NC castros (v7 tenia 15311 y 960)"
if [ "$NC" -lt 1500 ]; then
  say "*** solo $NC castros: la descarga no rindio lo esperado, abortando ***"; exit 1
fi

say "=== 2. anadiendo los negativos duros minados ==="
FPA=""
for B in lugo coruna ourense pontevedra; do
  [ -f "data/fp_${B}.tsv" ] && FPA="$FPA data/fp_${B}.tsv:data/external/lidar-val-$B"
done
if [ -n "$FPA" ]; then
  .venv-gpu/bin/python scripts/minar_negativos_duros.py \
    --fp $FPA --corpus data/galicia-vignettes-v11 \
    --salida data/galicia-vignettes-v11b --grupo hard_negative_barrido \
    --workers 3 >> "$LOG" 2>&1
  say "negativos duros rc=$?"
  CORPUS=data/galicia-vignettes-v11b
else
  CORPUS=data/galicia-vignettes-v11
fi

say "=== 3. entrenando v11 sobre $CORPUS ==="
.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir "$CORPUS" --out-dir data/cls-v11 \
  --head cls --encoder resnet34 --epochs 16 --batch 16 --workers 4 \
  --loss focal --focal-gamma 2.0 --peso-negativo-duro 8 >> "$LOG" 2>&1
RC=$?; say "entrenamiento rc=$RC"
[ "$RC" -ne 0 ] && { say "*** ENTRENAMIENTO v11 FALLO ***"; exit "$RC"; }

say "=== 4. criba barata antes de gastar 10 h de barrido ==="
say "  interna de referencia: v7 = 0.4605"
INT=$(grep -aoE "selección [0-9.]+" "$LOG" | sort -t" " -k2 -rn | head -1 | grep -oE "[0-9.]+")
say "  interna de v11 = $INT"

say "=== 5. barriendo los cuatro bloques ==="
for B in lugo coruna ourense pontevedra; do
  case $B in
    lugo) BB="-7.375 42.625 -7.125 42.875";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
    coruna) BB="-8.50 43.00 -8.25 43.25";;
    ourense) BB="-8.25 42.25 -8.00 42.50";;
  esac
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-val-$B --checkpoint data/cls-v11/best.pt \
    --out data/sweep_val_${B}_v11.tsv --bbox $BB \
    --workers 2 --batch 16 --chunk 100 --max-celdas-tarea 30 >> "$LOG" 2>&1
  say "barrido $B rc=$?"
  say "=== EVALUACION $B con v11, metro fusionado ==="
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_val_${B}_v11.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv --umbrales 0.5 0.7 0.8 0.9 >> "$LOG" 2>&1
  .venv-gpu/bin/python scripts/extraer_candidatos.py \
    --pred data/sweep_val_${B}_v11.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv --umbral 0.7 \
    --out data/candidatos_${B}_v11.tsv >> "$LOG" 2>&1
done
say "=== referencia v7: F1 medio 0.512 ==="
say "### v11 completa ###"
