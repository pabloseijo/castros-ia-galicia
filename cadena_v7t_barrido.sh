#!/bin/bash
# Barre y evalua v7t, que es v7 con UNA sola variable cambiada: `--translate 128`.
#
# La hipotesis tiene medida propia detras, no analogia. En v3 se comprobo que un
# castro CENTRADO en la vinneta puntua mediana `0,988`, y el MISMO castro visto
# desde la celda del barrido —descentrado, que es como llega siempre en
# despliegue— puntua `0,386` y roza el umbral. Los negativos no se mueven:
# `0,030` a `0,024`. Descentrar destruye solo la senal positiva.
#
# v7 se entreno SIN esa augmentacion, asi que aprendio a reconocer castros
# centrados y se despliega sobre celdas que nunca lo estan.
#
# **El 128 no es un numero elegido a ojo: sale de la rejilla.** El barrido usa
# ventanas de `512 m` con paso de `256 m` (`--extent-m 512`, `step = extent/2`),
# asi que en despliegue cualquier punto del terreno cae como mucho a `128 m` del
# centro de alguna celda, en cada eje. Con `--translate 128` y `dy, dx`
# independientes en `[-128, 128]`, la augmentacion reproduce exactamente la
# distribucion de descentrado que la rejilla produce, ni mas ni menos. Si algun
# dia cambia `--step-m`, este valor cambia con el.
#
# Ademas v7 sobreajusta
# —la perdida de entrenamiento cae de 0,306 a 0,133 mientras la metrica de
# validacion toca techo en la epoca 9 y termina por debajo— y `translate` es
# tambien regularizacion.
#
# Va detras de la cadena de v8 a proposito: v8 es el experimento con mejor
# justificacion fisica (el cuarto canal de apertura) y tiene preferencia por la
# GPU. Este espera a que aquel termine.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v7t.log
mkdir -p logs
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

say "### barrido y evaluacion de v7t ###"

say "=== esperando a que v7t termine de entrenarse ==="
while pgrep -f "train_unet[_]multiclass.py" > /dev/null 2>&1; do sleep 60; done
if [ ! -f data/cls-v7t/best.pt ]; then
  say "*** no hay data/cls-v7t/best.pt: v7t no llego a entrenarse ***"; exit 1
fi
say "checkpoint v7t: $(stat -c %y data/cls-v7t/best.pt | cut -c1-16)"

# La cadena de v8 tiene preferencia: si esta corriendo o aun le queda, se espera.
say "=== cediendo la GPU a la cadena de v8 si sigue viva ==="
while pgrep -f "cadena[_]v8.sh" > /dev/null 2>&1; do sleep 120; done
while pgrep -f "train_unet[_]multiclass.py|sweep_grid[_]lidar.py" > /dev/null 2>&1; do sleep 60; done
sleep 10

say "=== barriendo los cuatro bloques con v7t ==="
for B in lugo coruna ourense pontevedra; do
  case $B in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
  esac
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-val-$B --checkpoint data/cls-v7t/best.pt \
    --out data/sweep_val_${B}_v7t.tsv --bbox $BB \
    --workers 2 --batch 16 --chunk 200 >> "$LOG" 2>&1
  RC=$?
  say "barrido $B rc=$RC"
  [ "$RC" -ne 0 ] && { say "*** BARRIDO $B FALLO: no se evalua ***"; continue; }

  say "--- $B con v7t, metro fusionado ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_val_${B}_v7t.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv \
    --umbrales 0.5 0.7 0.8 0.9 >> "$LOG" 2>&1

  say "--- candidatos sin catalogar de $B con v7t ---"
  .venv-gpu/bin/python scripts/extraer_candidatos.py \
    --pred data/sweep_val_${B}_v7t.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv --umbral 0.7 \
    --out data/candidatos_${B}_v7t.tsv >> "$LOG" 2>&1
done

say "=== referencia v7, metro fusionado, umbral 0.70 ==="
say "  Lugo prec 0.826 F1 0.697 | Coruna 0.769/0.396 | Ourense 0.543/0.535 | Pontevedra 0.391/0.419"
say "### v7t completa ###"
