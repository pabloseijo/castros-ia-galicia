#!/bin/sh
# Repesca de los bloques de v9 que se quedaron sin barrer, con REINTENTO.
#
# Por qué existe: `gpu_libre.sh` comprueba y devuelve, pero el barrido tarda
# segundos en cargar torch, y en ese hueco otro proceso puede tomar la GPU. Es
# la carrera de comprobar-y-luego-actuar, y pasó dos veces el 2026-08-10:
#
#   [20:09] GPU libre  -> lugo    -> CUDA error: device busy -> rc=1, 0 filas
#   [20:14] GPU libre  -> ourense -> bien
#
# Comprobar mejor no lo arregla: la carrera es inherente. Lo que lo arregla es
# **reintentar**, que además hace la cadena inmune a que el entrenamiento de voz
# de Pablo vaya y venga.
set -u
cd "$(dirname "$0")/.." || exit 1
LOG=logs/cadena_v9_repesca.log
say() { echo "[$(date +%F\ %H:%M)] $*" | tee -a "$LOG"; }

INTENTOS=6
# **6500M y no 4000M.** El arreglo del `float64` del 2026-08-11 duplica los
# arrays de coordenadas —x e y pasan de 4 a 8 bytes por punto— y con eso
# el barrido de 7 canales de Coruna toco el tope de 4 GB y murio por OOM
# a las 901 de 8.619 filas. La memoria de mas es real y hay que darsela.

say "esperando a que la cadena principal de v9 termine"
until grep -q '### cadena v9 terminada ###' logs/cadena_v9_completa.log 2>/dev/null \
      && ! pgrep -f cadena_v9_completa.sh > /dev/null; do
  sleep 120
done
say "cadena principal cerrada; empieza la repesca"

completo() {          # $1 = bloque
  N=$(wc -l < "data/sweep_val_${1}_v9.tsv" 2>/dev/null || echo 0)
  R=$(wc -l < "data/sweep_val_${1}_v7.tsv" 2>/dev/null || echo 999999)
  [ "$N" -ge $((R * 9 / 10)) ]
}

for B in lugo ourense coruna; do
  case "$B" in
    lugo)    BB="-7.375 42.625 -7.125 42.875";;
    coruna)  BB="-8.50 43.00 -8.25 43.25";;
    ourense) BB="-8.25 42.25 -8.00 42.50";;
  esac
  OUT="data/sweep_val_${B}_v9.tsv"

  I=1
  while [ "$I" -le "$INTENTOS" ]; do
    if completo "$B"; then
      say "$B ya completo ($(wc -l < "$OUT") filas)"
      break
    fi
    # **Guarda contra dos barridos del mismo bloque.** Si ya hay uno vivo
    # -por ejemplo de una corrida anterior de esta misma cadena- lanzar otro
    # escribiria dos procesos sobre el mismo TSV. Se espera a que termine.
    if pgrep -f "sweep_grid_lidar.py.*lidar-val-$B" > /dev/null; then
      say "$B: ya hay un barrido vivo, espero a que acabe"
      while pgrep -f "sweep_grid_lidar.py.*lidar-val-$B" > /dev/null; do sleep 120; done
      say "$B: el barrido anterior ha terminado"
      continue
    fi
    if ! scripts/gpu_libre.sh; then
      say "$B intento $I: GPU ocupada, espero"
      until scripts/gpu_libre.sh; do sleep 180; done
    fi
    say "=== $B intento $I de $INTENTOS ==="
    CASTROS_VRAM_FRAC=0.45 scripts/lanzar.sh "barrido-$B-v9r$I" 6500M \
      .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
      --laz-dir "data/external/lidar-val-$B" --checkpoint data/cls-v9/best.pt \
      --out "$OUT" --bbox $BB \
      --ortofoto-dir data/ortofotos-rejilla --ortofoto-prefijo "${B}_" \
      --workers 1 --batch 12 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
    RC=$?
    say "$B intento $I rc=$RC filas=$(wc -l < "$OUT" 2>/dev/null || echo 0)"
    # El barrido REANUDA, así que un intento fallido no pierde lo ya hecho.
    [ "$RC" -eq 0 ] && completo "$B" && break
    I=$((I + 1))
    sleep 120
  done

  if completo "$B"; then
    say "--- evaluacion de $B ---"
    .venv-gpu/bin/python scripts/detection_eval.py \
      --pred "$OUT" --truth "data/${B}_fus_truth_limpia.tsv" \
      --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
  else
    say "*** $B NO se completo tras $INTENTOS intentos ***"
  fi
done

say "=== resumen con cobertura ==="
.venv-gpu/bin/python scripts/f1_con_cobertura.py >> "$LOG" 2>&1
say "### repesca v9 terminada ###"
