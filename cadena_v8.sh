#!/bin/bash
# v8 = v7 mas el cuarto canal de apertura topografica.
#
# Es el cuello de botella con mejor justificacion de los encontrados el
# 2026-08-07, y el unico que viene con explicacion fisica de por que deberia
# funcionar en vez de con una analogia.
#
# El caso que lo motiva: el candidato OU-8 tenia el mejor perfil topografico de
# los 27 de Ourense —49,3 m de prominencia, 100% del entorno debajo, plataforma
# llana— y en el sombreado se veian arcos concentricos envolviendo la cima. Eran
# PISTAS FORESTALES, y lo delato la ortofoto. Los tres canales del modelo —MDT
# normalizado, relieve local y pendiente— no tienen forma de distinguirlas de un
# parapeto: una pista es un CORTE, un rasgo lineal fino de un tono, mientras que
# un parapeto es CABALLON MAS FOSO, un alto y un bajo pegados.
#
# La apertura (Doneus 2013, 10.3390/rs5126427) resalta a la vez lo mas alto y lo
# mas bajo, que es exactamente esa firma. Verificado sobre dato propio: un castro
# conocido de Ourense sale como anillo cerrado de tono doble y OU-8 como lineas
# finas de tono unico.
#
# La comparacion con v7 es limpia: mismo corpus de sitios, misma perdida, mismo
# barrido. Lo unico que cambia es el canal.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v8.log
mkdir -p logs
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

say "### v8: cuarto canal de apertura ###"

say "=== esperando a que termine de cortarse el corpus ==="
while pgrep -f "build[_]trasancos[_]vignettes.py" > /dev/null 2>&1; do sleep 120; done
N=$(( $(wc -l < data/galicia-vignettes-v8/index.tsv 2>/dev/null || echo 1) - 1 ))
say "corpus v8: $N vinnetas"
if [ "$N" -lt 10000 ]; then
  say "*** corpus incompleto ($N): abortando ***"; exit 1
fi

# Los negativos agricolas de v7 hay que volver a cortarlos CON el canal, o la
# red recibiria vinnetas de 3 y de 4 canales en el mismo lote.
if [ -f data/negativos-osm-ourense.tsv ]; then
  say "=== cortando los negativos agricolas con el cuarto canal ==="
  .venv-gpu/bin/python scripts/minar_negativos_duros.py \
    --fp data/negativos-osm-ourense.tsv:data/external/lidar-val-ourense \
    --corpus data/galicia-vignettes-v8 --salida data/galicia-vignettes-v8b \
    --grupo hard_negative_agricola --workers 3 --con-apertura >> "$LOG" 2>&1
  say "corte rc=$?"
  CORPUS=data/galicia-vignettes-v8b
else
  CORPUS=data/galicia-vignettes-v8
fi
say "corpus final: $CORPUS ($(( $(wc -l < $CORPUS/index.tsv) - 1 )) vinnetas)"

say "=== esperando GPU ==="
while pgrep -f "train_unet[_]multiclass.py|sweep_grid[_]lidar.py" > /dev/null 2>&1; do sleep 60; done
sleep 10

say "=== entrenando v8 ==="
.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir "$CORPUS" --out-dir data/cls-v8 \
  --head cls --encoder resnet34 --epochs 16 --batch 16 --workers 4 \
  --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
RC=$?
say "entrenamiento rc=$RC"
[ "$RC" -ne 0 ] && { say "*** ENTRENAMIENTO FALLO ***"; exit "$RC"; }

say "=== barriendo y evaluando los cuatro bloques ==="
for B in lugo pontevedra coruna ourense; do
  case $B in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
  esac
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-val-$B --checkpoint data/cls-v8/best.pt \
    --out data/sweep_val_${B}_v8.tsv --bbox $BB \
    --workers 2 --batch 16 --chunk 200 >> "$LOG" 2>&1
  RC=$?
  say "barrido $B rc=$RC"
  [ "$RC" -ne 0 ] && { say "*** BARRIDO $B FALLO: no se evalua ***"; continue; }

  say "--- $B con v8, metro fusionado ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_val_${B}_v8.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv \
    --umbrales 0.5 0.7 0.8 0.9 >> "$LOG" 2>&1

  say "--- candidatos sin catalogar de $B ---"
  .venv-gpu/bin/python scripts/extraer_candidatos.py \
    --pred data/sweep_val_${B}_v8.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv --umbral 0.7 \
    --out data/candidatos_${B}_v8.tsv >> "$LOG" 2>&1
done

say "=== referencia v7, metro fusionado, umbral 0.70 ==="
say "  Lugo prec 0.826 F1 0.697 | Coruna 0.769/0.396 | Ourense 0.543/0.535 | Pontevedra 0.391/0.419"
say "### v8 completa ###"
