#!/bin/sh
# v14: los mismos datos de v11p, sin la confusion espacial que los inutilizaba.
#
# Ver `docs/preregistros/PREREGISTRO-v14-confusion-espacial.md`. En corto: el `53%` de los positivos
# de v11p vivia en bloques de los que el modelo no veia **ni una viñeta de
# fondo**, y en su examen ese numero subia al `72%`. Eso es un atajo —reconocer
# el sitio, no el yacimiento— que en el barrido real no existe, porque el barrido
# recorre todas las celdas del bloque, castro incluido.
#
# La prueba de que el atajo estaba ahi: **la misma arquitectura saca `0,72`-`0,81`
# en el examen contaminado de v11p y `0,46` en el examen limpio de v7**.
#
# v14 = v11p menos los positivos huerfanos de fondo, repartido de nuevo por
# bloques enteros. `988` castros de entrenamiento contra los `773` de v7: un
# `28%` mas, y esta vez sin el atajo.
#
# **No corta ni descarga nada**: las viñetas ya existen en v11p.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v14.log
say() { echo "[$(date +%F' '%H:%M)] $*" >> "$LOG"; }

say "### cadena v14: quitar la confusion espacial ###"

# El nodo tiene 8 GB y hoy ya se han perdido barridos por amontonar trabajos.
say "esperando a que v12 suelte el nodo (entreno y barridos)"
while systemctl --user list-units 'castros-*' --no-legend --no-pager 2>/dev/null \
      | grep -qE 'castros-(entreno|barrido|corpus)'; do
  sleep 180
done
say "nodo libre"

# --- 1. corpus (filtro de indice, sin cortar) ---
if [ ! -s data/galicia-vignettes-v14/index.tsv ]; then
  say "=== construyendo el indice de v14 ==="
  nice -n 10 .venv-gpu/bin/python scripts/construir_v14.py >> "$LOG" 2>&1
fi
[ -s data/galicia-vignettes-v14/index.tsv ] || { say "*** sin corpus: abortando ***"; exit 1; }

POS=$(awk -F'\t' 'NR>1 && $3 ~ /^castro/ {n++} END{print n+0}' data/galicia-vignettes-v14/index.tsv)
say "corpus v14: $POS castros"
# v7 tiene 953 castros en total (773 train + 180 val). v14 debe tener mas, o el
# filtro se ha comido lo que venia a salvar y el experimento no dice nada.
if [ "$POS" -lt 1000 ]; then
  say "*** solo $POS castros, menos de los que justifican el experimento: abortando ***"
  exit 1
fi

# --- 2. controles del preregistro ---
CTRL=logs/controles_v14_$(date +%H%M%S).txt
say "=== controles -> $CTRL ==="
.venv-gpu/bin/python scripts/controles_v11.py \
  --nuevo data/galicia-vignettes-v14 --referencia data/galicia-vignettes-v7 \
  --val-distinta-a-proposito "v14 reparte de nuevo para sacar del examen la confusion espacial de v11p (72% de sus castros de val vivian en bloques sin fondo). Se compara por despliegue en los cuatro bloques, no por selection_best." \
  > "$CTRL" 2>&1
cat "$CTRL" >> "$LOG"
if grep -q "FALLA" "$CTRL"; then
  say "*** CONTROLES FALLAN: abortando ***"; exit 1
fi
say "controles pasados; precinto cerrado"

# --- 3. entrenar ---
say "=== entrenando v14 ==="
CASTROS_VRAM_FRAC=0.80 scripts/lanzar.sh entreno-v14 4G \
  .venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v14 --out-dir data/cls-v14 \
  --head cls --encoder resnet34 --epochs 16 --batch 16 --workers 2 \
  --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
say "entrenamiento v14 rc=$?"
[ -f data/cls-v14/best.pt ] || { say "*** sin checkpoint: abortando ***"; exit 1; }

# --- 4. barrer los cuatro bloques ---
# Los bbox **se copian, nunca se escriben de memoria**: el 2026-08-08 se tecleo
# uno mal y se barrio otro sitio de Galicia durante horas, con cifras que
# parecian validas.
say "=== barridos de v14 ==="
sed 's/v13/v14/g' scripts/barridos_v13.sh > scripts/barridos_v14.sh
chmod +x scripts/barridos_v14.sh
scripts/barridos_v14.sh
say "### cadena v14 terminada ###"
