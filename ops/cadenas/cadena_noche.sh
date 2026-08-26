#!/bin/bash
# La noche entera en UNA cadena, secuencial y sin huecos.
#
# Antes eran tres guiones esperandose entre si por `pgrep`, y eso tenia dos
# fallos que ya se pagaron el 2026-08-07 y el 08:
#   - dos podian despertar en la misma ventana de `sleep` y arrancar juntos, en
#     una maquina de 8 GB donde apilar trabajos ya costo hora y media;
#   - matar el envoltorio no mataba el guion lanzado con `setsid`, asi que una
#     cadena zombi arranco a barrer por su cuenta con la RAM al limite.
#
# Con un solo proceso secuencial no hay ventana ni zombi: lo que corre es lo que
# pone aqui, en este orden.
#
# ORDEN, y por que:
#   1. barridos de v8   — el experimento con justificacion fisica (apertura)
#   2. barridos de v7t  — cierra un compromiso preregistrado, y es rapido
#   3. v9               — la linea nueva, larga, y la que depende de quien gane
#
# Los barridos son REANUDABLES: saltan las celdas ya puntuadas. Lugo lleva 1.328
# de v8 salvadas de antes del OOM.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_noche.log
mkdir -p logs
say() { echo "[$(date +%H:%M)] $*" | tee -a "$LOG"; }

BLOQUES="lugo coruna ourense pontevedra"
bbox_de() {
  case $1 in
    lugo)       echo "-7.375 42.625 -7.125 42.875";;
    pontevedra) echo "-8.875 42.125 -8.625 42.375";;
    coruna)     echo "-8.50 43.00 -8.25 43.25";;
    ourense)    echo "-8.25 42.25 -8.00 42.50";;
  esac
}

# `--max-celdas-tarea 30`: acota el recuadro union que carga cada obrero. El
# 2026-08-08 uno llego a 4,86 GB y el OOM killer se llevo cuatro horas de
# barrido. Con 2 obreros y este techo, el pico por obrero se queda muy por
# debajo de lo que hay libre.
barre() {
  local mod=$1 bloque=$2 extra=$3
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-val-$bloque \
    --checkpoint data/cls-$mod/best.pt \
    --out data/sweep_val_${bloque}_${mod}.tsv --bbox $(bbox_de $bloque) \
    --workers 2 --batch 16 --chunk 100 --max-celdas-tarea 30 $extra \
    >> "$LOG" 2>&1
  local rc=$?
  say "barrido $bloque con $mod rc=$rc"
  [ "$rc" -ne 0 ] && return "$rc"
  say "=== EVALUACION $bloque con $mod, metro fusionado ==="
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_val_${bloque}_${mod}.tsv \
    --truth data/${bloque}_fus_truth_limpia.tsv \
    --mascara data/${bloque}_fus_mascara_train.tsv \
    --umbrales 0.5 0.7 0.8 0.9 >> "$LOG" 2>&1
  .venv-gpu/bin/python scripts/extraer_candidatos.py \
    --pred data/sweep_val_${bloque}_${mod}.tsv \
    --truth data/${bloque}_fus_truth_limpia.tsv \
    --mascara data/${bloque}_fus_mascara_train.tsv --umbral 0.7 \
    --out data/candidatos_${bloque}_${mod}.tsv >> "$LOG" 2>&1
  return 0
}

say "###################### CADENA DE NOCHE ######################"
say "referencia v7 (metro fusionado, umbral 0.70): F1 medio 0.512"
say "  Lugo 0.826/0.697 | Coruna 0.769/0.396 | Ourense 0.543/0.535 | Pontevedra 0.391/0.419"

say "===================== 1. v8 (4 canales) ====================="
for B in $BLOQUES; do barre v8 "$B" ""; done
say "### v8 completa ###"

say "===================== 2. v7t (traslacion) ==================="
if [ -f data/cls-v7t/best.pt ]; then
  for B in $BLOQUES; do barre v7t "$B" ""; done
  say "### v7t completa ###"
else
  say "*** falta cls-v7t/best.pt: se salta ***"
fi

say "===================== 3. v9 (7 canales) ====================="
NO=$(ls data/ortofotos-corpus 2>/dev/null | wc -l)
NR=$(ls data/ortofotos-rejilla 2>/dev/null | wc -l)
say "ortofotos: corpus $NO, rejilla $NR"
if [ "$NO" -lt 14000 ] || [ "$NR" -lt 30000 ]; then
  say "*** faltan ortofotos: v9 no se entrena ***"; exit 1
fi
say "=== entrenando v9 ==="
.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v8 --rgb-dir data/ortofotos-corpus \
  --out-dir data/cls-v9 --head cls --encoder resnet34 \
  --epochs 16 --batch 12 --workers 3 --loss focal --focal-gamma 2.0 \
  >> "$LOG" 2>&1
RC=$?; say "entrenamiento v9 rc=$RC"
if [ "$RC" -eq 0 ]; then
  for B in $BLOQUES; do
    barre v9 "$B" "--ortofoto-dir data/ortofotos-rejilla --ortofoto-prefijo ${B}_"
  done
  say "### v9 completa ###"
fi

say "###################### NOCHE COMPLETA ######################"
