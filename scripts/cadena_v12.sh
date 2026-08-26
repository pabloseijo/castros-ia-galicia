#!/bin/sh
# v12: los 524 errores reales de v7 añadidos a su propio corpus, con peso 1.
#
# Ver `docs/preregistros/PREREGISTRO-v12-mineria.md`. En corto: es la palanca de Canedo —que paso de
# `5.678` falsos positivos a `40` minando los fallos del propio modelo— y es lo
# unico que la literatura demuestra para este objeto exacto.
#
# **Peso `1`, no `8`.** v10 puso `8` y hundio el recall de castro de `0,722` a
# `0,256`. Lo que trabaja es la cantidad y la especificidad de los negativos, no
# un multiplicador.
#
# **Sobre el corpus de v7**, no el de v11p: v11p esta refutado (`0,390` contra
# `0,512`) y minar sobre el arrastraria su desbalance de proporcion.
#
# Espera a que terminen los barridos de v13 antes de empezar: el nodo tiene
# `7,3 GB` y hoy se han perdido tres barridos por amontonar.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v12.log
say() { echo "[$(date +%F' '%H:%M)] $*" >> "$LOG"; }

say "### cadena v12: mineria sobre v7 ###"

say "esperando a que terminen los barridos de v13"
while systemctl --user list-units "castros-barrido-*" --no-legend --no-pager 2>/dev/null | grep -q running; do
  sleep 180
done
say "barridos libres"

# --- 1. corpus: v7 + los 524 negativos minados ---
if [ ! -s data/galicia-vignettes-v12/index.tsv ]; then
  say "=== cortando las viñetas de los negativos minados ==="
  # **`--fp` quiere `fichero:directorio_laz`, uno por bloque.** Cada falso
  # positivo necesita el LiDAR de SU zona para poder cortarle la viñeta, asi que
  # un fichero fusionado de los cuatro bloques no vale: pierde esa asociacion y el
  # guion revienta con `not enough values to unpack`. Fue el primer intento.
  FPS=""
  for B in lugo coruna ourense pontevedra; do
    F="data/fp_${B}_v7_min.tsv"
    [ -s "$F" ] && FPS="$FPS $F:data/external/lidar-val-$B"
  done
  say "ficheros de negativos:$FPS"
  nice -n 10 scripts/lanzar.sh corpus-v12 4G \
    .venv-gpu/bin/python scripts/minar_negativos_duros.py \
    --fp $FPS --corpus data/galicia-vignettes-v7 \
    --salida data/galicia-vignettes-v12 --grupo hard_negative_barrido \
    --workers 2 >> "$LOG" 2>&1
  say "corpus v12 rc=$?"
fi
[ -s data/galicia-vignettes-v12/index.tsv ] || { say "*** sin corpus: abortando ***"; exit 1; }

N=$(( $(wc -l < data/galicia-vignettes-v12/index.tsv) - 1 ))
NUEVOS=$(awk -F'\t' 'NR>1 {gsub(/\r/,""); if ($3 ~ /hard_negative_barrido/) n++} END{print n+0}' data/galicia-vignettes-v12/index.tsv)
say "corpus v12: $N viñetas | $NUEVOS negativos minados nuevos"
if [ "$NUEVOS" -lt 300 ]; then
  say "*** solo $NUEVOS negativos minados (se esperaban ~524): abortando ***"
  exit 1
fi

# --- 2. controles del preregistro ---
CTRL=logs/controles_v12_$(date +%H%M%S).txt
say "=== controles -> $CTRL ==="
.venv-gpu/bin/python scripts/controles_v11.py --nuevo data/galicia-vignettes-v12 \
  --referencia data/galicia-vignettes-v7 > "$CTRL" 2>&1
cat "$CTRL" >> "$LOG"
if grep -q "FALLA:.*sellados\|precinto: NO se puede comprobar" "$CTRL"; then
  say "*** PRECINTO COMPROMETIDO: abortando ***"; exit 1
fi
say "precinto verificado cerrado"

# --- 3. entrenar ---
say "=== entrenando v12 (peso 1) ==="
CASTROS_VRAM_FRAC=0.80 scripts/lanzar.sh entreno-v12 4G \
  .venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v12 --out-dir data/cls-v12 \
  --head cls --encoder resnet34 --epochs 16 --batch 16 --workers 2 \
  --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
say "entrenamiento v12 rc=$?"
[ -f data/cls-v12/best.pt ] || { say "*** sin checkpoint: abortando ***"; exit 1; }

# --- 4. barrer los cuatro bloques ---
say "=== barridos de v12 ==="
sed 's/v13/v12/g' scripts/barridos_v13.sh > scripts/barridos_v12.sh
chmod +x scripts/barridos_v12.sh
scripts/barridos_v12.sh
say "### cadena v12 terminada ###"
