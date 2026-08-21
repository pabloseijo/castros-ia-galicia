#!/bin/bash
# v7: todo lo aprendido el 6 y 7 de agosto, junto, sobre los cuatro bloques.
#
# Lo que cambia respecto a v6-focal:
#
#   1. **Negativos agricolas.** Ourense salio a 0.372 —como la ria de Vigo pese
#      a ser interior rural— y su confusor no es obra moderna sino vinnedo en
#      bancales. Las diez familias de OSM que habia eran todas modernas; se
#      anaden vinnedo, frutal y bancal, con la guarda de no coger nada a menos
#      de 250 m de un castro conocido (una ladera de castro cultivada
#      etiquetada como negativo ensena a la red a apagar lo que busca).
#
#   2. **Focal loss**, que ya estaba en v6-focal y se conserva: a recall
#      igualado subio la precision de Pontevedra un 42% y apago todos los
#      falsos positivos nuevos.
#
#   3. **Barrido 1,70x mas rapido** con resultado identico: cache de 8 teselas
#      —el comentario decia 400 MB cada una y son 20— y lotes de 200 tareas
#      consecutivas para que las que comparten tesela caigan en el mismo obrero.
#
#   4. **Criba de ortofoto** despues del barrido, para el confusor moderno:
#      4 de los 5 falsos positivos que sobreviven en Pontevedra son nucleo
#      urbano, autovia, poligono o la pista del aeropuerto de Vigo.
#
# NO toca el precinto de Portugal.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v7.log
mkdir -p logs
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

say "### v7 ###"

say "=== esperando a que la GPU y las descargas queden libres ==="
while pgrep -f "train_unet[_]multiclass.py|sweep_grid[_]lidar.py|criba[_]ortofoto.py" > /dev/null 2>&1; do sleep 60; done
sleep 10

# --- 1. corpus v7 = v6 + negativos agricolas -------------------------------
if [ -f data/negativos-osm-ourense.tsv ]; then
  N=$(( $(wc -l < data/negativos-osm-ourense.tsv) - 1 ))
  say "negativos agricolas de Ourense: $N"
  say "=== cortando vinnetas nuevas ==="
  .venv-gpu/bin/python scripts/minar_negativos_duros.py \
    --fp data/negativos-osm-ourense.tsv:data/external/lidar-val-ourense \
    --corpus data/galicia-vignettes-v6 --salida data/galicia-vignettes-v7 \
    --grupo hard_negative_agricola --workers 3 >> "$LOG" 2>&1
  say "corte rc=$?"
  CORPUS=data/galicia-vignettes-v7
else
  say "AVISO: no hay negativos de Ourense; v7 usa el corpus de v6"
  CORPUS=data/galicia-vignettes-v6
fi
say "corpus: $CORPUS ($(( $(wc -l < $CORPUS/index.tsv) - 1 )) vinnetas)"

# --- 2. entrenar -----------------------------------------------------------
say "=== entrenando v7 (focal loss) ==="
.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir "$CORPUS" --out-dir data/cls-v7 \
  --head cls --encoder resnet34 --epochs 16 --batch 16 --workers 4 \
  --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
RC=$?
say "entrenamiento rc=$RC"
[ "$RC" -ne 0 ] && { say "*** ENTRENAMIENTO FALLO: abortando ***"; exit "$RC"; }

# --- 3. barrer y evaluar los cuatro bloques --------------------------------
for B in lugo pontevedra coruna ourense; do
  case $B in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
  esac
  say "--- barriendo $B ---"
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-val-$B --checkpoint data/cls-v7/best.pt \
    --out data/sweep_val_${B}_v7.tsv --bbox $BB \
    --workers 2 --batch 16 --chunk 200 >> "$LOG" 2>&1
  RC=$?
  say "barrido $B rc=$RC"
  [ "$RC" -ne 0 ] && { say "*** BARRIDO $B FALLO: no se evalua ***"; continue; }

  say "--- $B con v7, SIN criba ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_val_${B}_v7.tsv --truth data/${B}_truth_limpia.tsv \
    --mascara data/${B}_mascara_train.tsv --umbrales 0.5 0.7 0.8 0.9 >> "$LOG" 2>&1
done

say "=== referencias ==="
say "v3:       Lugo prec 0.808 | Pontevedra 0.179"
say "v6-focal: Lugo 0.791 | Coruna 0.641 | Ourense 0.372 | Pontevedra 0.200  (umbral 0.70)"
say "### v7 completa ###"
