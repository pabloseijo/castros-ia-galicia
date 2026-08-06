#!/bin/bash
# Barre A Coruna y Ourense, los dos bloques que cierran Galicia.
#
# NO se lanza solo a proposito. Que checkpoint usar depende de que gane entre
# v6 y v6-focal, y eso es una decision, no un automatismo. Se ejecuta a mano:
#
#     ./barrer_bloques_nuevos.sh data/cls-v6-focal/best.pt v6focal
#
# Requiere que la descarga haya terminado (descargar_bloques_galicia.sh) y
# comprueba que hay teselas antes de gastar dos horas de GPU.
#
# La verdad de campo ya esta preparada (2026-08-07):
#   coruna   70 castros nunca vistos, 35 enmascarados  (Ordes, Frades, Cerceda)
#   ourense  34 castros nunca vistos, 21 enmascarados  (Cenlle, San Amaro, Punxin)
set -u
[ $# -ge 2 ] || { echo "uso: $0 <checkpoint> <etiqueta>"; exit 2; }
CKPT="$1"; ETQ="$2"
cd "$HOME/castros" || exit 1
LOG="logs/barrido_bloques_nuevos_${ETQ}.log"
mkdir -p logs
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

[ -f "$CKPT" ] || { say "no existe el checkpoint $CKPT"; exit 1; }

say "=== esperando a que la GPU quede libre ==="
while pgrep -f "train_unet_multiclass.py|sweep_grid_lidar.py" > /dev/null 2>&1; do sleep 60; done
say "=== esperando a que terminen las descargas ==="
while pgrep -f "descargar_bloques_galicia.sh|download_trasancos_lidar.py" > /dev/null 2>&1; do sleep 120; done

for B in coruna ourense; do
  case $B in
    coruna)  BB="-8.50 43.00 -8.25 43.25";;
    ourense) BB="-8.25 42.25 -8.00 42.50";;
  esac
  N=$(ls data/external/lidar-val-$B/*.laz 2>/dev/null | wc -l)
  if [ "$N" -lt 100 ]; then
    say "*** $B tiene solo $N teselas: descarga incompleta, NO se barre ***"
    continue
  fi
  say "--- barriendo $B con $CKPT ($N teselas) ---"
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-val-$B --checkpoint "$CKPT" \
    --out data/sweep_val_${B}_${ETQ}.tsv --bbox $BB --workers 2 --batch 16 >> "$LOG" 2>&1
  RC=$?
  say "barrido $B rc=$RC"
  [ "$RC" -ne 0 ] && { say "*** BARRIDO $B FALLO: no se evalua ***"; continue; }

  say "--- $B con $ETQ ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_val_${B}_${ETQ}.tsv --truth data/${B}_truth_limpia.tsv \
    --mascara data/${B}_mascara_train.tsv --umbrales 0.5 0.7 0.8 0.9 >> "$LOG" 2>&1
done
say "=== bloques nuevos completos ==="
say "referencia v3: Lugo prec 0.808 F1 0.743 | Pontevedra prec 0.179 F1 0.274"
