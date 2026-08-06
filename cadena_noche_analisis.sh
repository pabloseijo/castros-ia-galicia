#!/bin/bash
# Todo lo que se puede medir sin decidir nada, encadenado para la noche.
#
# Espera a que el barrido de v6-focal termine y entonces responde la pregunta
# que decide la via del proyecto: los falsos positivos que quedan, ¿son sitios
# que el entrenamiento YA VIO etiquetados como negativo?
#
# Linea base medida con v6 (CrossEntropyLoss balanceado), umbral 0.80:
#   26 falsos positivos, de los que 23 (88%) ya se habian visto como negativo.
#
# Si con focal loss ese 88% baja mucho -> era el peso, la via de los negativos
# sigue viva y hay que seguir por ahi.
# Si se queda donde esta -> el relieve no distingue estos confusores por mucho
# que se insista, y toca la ortofoto como cuarto canal.
#
# NO decide nada ni toca el precinto de Portugal. Solo mide y escribe.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/noche_analisis.log
mkdir -p logs reports
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

say "### esperando a que termine la cadena v6-focal ###"
while pgrep -f 'cadena_v6_focal.sh' > /dev/null 2>&1; do sleep 120; done
say "cadena v6-focal terminada"

# --- 1. ¿Se apagaron los negativos que el modelo ya habia visto? -------------
for B in pontevedra lugo; do
  for V in v6 v6focal; do
    P="data/sweep_val_${B}_${V}.tsv"
    [ -f "$P" ] || { say "no existe $P, salto"; continue; }
    say "--- FP residuales | $B | $V ---"
    NEGS="data/fp_${B}.tsv"
    [ -f "data/negativos-osm-${B}.tsv" ] && NEGS="$NEGS data/negativos-osm-${B}.tsv"
    .venv-gpu/bin/python scripts/analizar_fp_residuales.py \
      --pred "$P" --truth "data/${B}_truth_limpia.tsv" \
      --mascara "data/${B}_mascara_train.tsv" \
      --negativos $NEGS --umbrales 0.7 0.8 >> "$LOG" 2>&1
    say "  rc=$?"
  done
done

# --- 2. Criba barata de checkpoints, que predice el barrido ------------------
# `eval_checkpoint_descentrado.py` puntua sobre validacion DESCENTRADA, que es
# la condicion del despliegue. Ya acerto una vez: predijo v3 > v4 y el barrido
# le dio la razon. Cuesta minutos en vez de las dos horas de un barrido.
say "--- criba descentrada de todos los checkpoints ---"
CKPTS=""
for D in cls-v3 cls-v5 cls-v6 cls-v6-focal; do
  [ -f "data/$D/best.pt" ] && CKPTS="$CKPTS data/$D/best.pt"
done
say "checkpoints: $CKPTS"
.venv-gpu/bin/python scripts/eval_checkpoint_descentrado.py \
  --vig-dir data/galicia-vignettes-v6 --ckpt $CKPTS --translate 128 >> "$LOG" 2>&1
say "  rc=$?"

say "### analisis de la noche completo ###"
