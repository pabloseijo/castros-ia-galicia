#!/bin/sh
# Los cuatro barridos de v11p, UNO detras de otro, con techo de memoria y cupo de
# VRAM. Es el veredicto de verdad: el liston del preregistro esta en el `F1` de
# barrido sobre los cuatro bloques, no en la metrica interna.
#
# **Los bbox se copian de `cadena_v7.sh`, NO se escriben de memoria.** El
# 2026-08-09 los de Lugo y Pontevedra se transcribieron mal —`-7.50 42.75` en vez
# de `-7.375 42.625`— y el barrido cubrio otro sitio: `2.520` celdas con LiDAR de
# `8.580` en vez de `8.800` de `8.800`. Los `F1 0,278` y `0,115` que salieron de
# ahi no eran «peores»: eran de otro trozo de Galicia. Si los cuatro bloques no
# son EXACTAMENTE los de v7, la comparacion no existe.
#
# **Por que en serie y no en paralelo.** El nodo tiene `8 GB` y cada barrido pica
# a `~3,5 GB` con dos obreros. El 2026-08-08 se lanzaron tres a la vez y murieron
# dos: uno con `CUDA out of memory` y otro con `BrokenProcessPool` cuando el OOM
# killer se llevo un obrero. En serie tardan mas y terminan.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/barridos_v11p.log
say() { echo "[$(date +%F' '%H:%M)] $*" >> "$LOG"; }

say "### barridos de v11p ###"
for B in lugo coruna ourense pontevedra; do
  case "$B" in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
  esac
  OUT="data/sweep_val_${B}_v11p.tsv"
  if [ -s "$OUT" ] && [ "$(wc -l < "$OUT")" -gt 100 ]; then
    say "SALTO $B: ya tiene $(wc -l < "$OUT") filas"
    continue
  fi
  say "=== barrido $B ==="
  # **UN obrero, no dos, y tareas de `12` celdas.** Con dos obreros uno solo llego
  # a `4,1 GB` y el conjunto a `6,7 GB` en una maquina de `7,3`: el barrido de
  # Lugo murio cuatro veces seguidas y solo completo el `10%` del bloque. Un
  # obrero tarda mas y TERMINA, que es lo unico que cuenta cuando el resultado se
  # necesita entero — un barrido al `10%` no es un barrido lento, es basura: dio
  # `F1 0.278` donde el modelo completo puede dar cualquier cosa.
  CASTROS_VRAM_FRAC=0.45 scripts/lanzar.sh "barrido-$B-v11p" 6000M \
    .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir "data/external/lidar-val-$B" --checkpoint data/cls-v11p/best.pt \
    --out "$OUT" --bbox $BB \
    --workers 1 --batch 12 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
  say "barrido $B rc=$?  filas=$(wc -l < "$OUT" 2>/dev/null || echo 0)"

  say "--- evaluacion de $B ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred "$OUT" --truth "data/${B}_fus_truth_limpia.tsv" \
    --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
done
# **Segunda pasada.** El bucle salta los bloques que ya tienen filas, asi que
# esta pasada solo reintenta los que fallaron —normalmente por memoria, y ahora
# con el nodo libre de competencia—. Sale gratis si no falló ninguno.
say "--- segunda pasada: reintento de los que quedaron a cero ---"
for B in lugo coruna ourense pontevedra; do
  OUT="data/sweep_val_${B}_v11p.tsv"
  [ -s "$OUT" ] && [ "$(wc -l < "$OUT")" -gt 100 ] && continue
  case "$B" in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
  esac
  say "=== reintento $B ==="
  CASTROS_VRAM_FRAC=0.45 scripts/lanzar.sh "reintento-$B-v11p" 6000M \
    .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir "data/external/lidar-val-$B" --checkpoint data/cls-v11p/best.pt \
    --out "$OUT" --bbox $BB \
    --workers 1 --batch 12 --chunk 100 --max-celdas-tarea 10 >> "$LOG" 2>&1
  say "reintento $B rc=$?  filas=$(wc -l < "$OUT" 2>/dev/null || echo 0)"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred "$OUT" --truth "data/${B}_fus_truth_limpia.tsv" \
    --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
done
say "### barridos de v11p terminados ###"
