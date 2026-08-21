#!/bin/sh
# Los cuatro barridos de v13, uno detras de otro, con los bbox de `cadena_v7.sh`.
#
# **Los bbox se copian, no se escriben de memoria.** El 2026-08-09 se
# transcribieron mal los de Lugo y Pontevedra y el barrido cubrio otro sitio:
# `2.520` celdas con LiDAR de `8.580` en vez de `8.658` de `8.658`. Los `F1` que
# salieron de ahi no eran «peores», eran de otro trozo de Galicia.
#
# **Un obrero, no dos.** Con dos, uno solo llego a `4,1 GB` y el conjunto a `6,7`
# en una maquina de `7,3`: Lugo murio cuatro veces y completo el `10%`. Un barrido
# al `10%` no es un barrido lento, es basura que ademas engaña.
#
# **La guarda compara contra el barrido de v7 del mismo bloque**, no contra un
# «>100 filas»: eso dio por completo un Pontevedra al `79%`.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/barridos_v13.log
say() { echo "[$(date +%F' '%H:%M)] $*" >> "$LOG"; }

say "### barridos de v13 ###"

# **Guarda de bbox, anadida el 2026-08-09.** El `2026-08-08` se teclearon mal los
# de Lugo y Pontevedra y se barrio otro trozo de Galicia durante horas, con `F1`
# que parecian perfectamente validos. Quedo escrita la regla «los bbox se copian,
# no se teclean» — pero una regla de disciplina se salta sola. Esto la comprueba
# contra el rango de coordenadas que **realmente** cubrio el barrido de v7, que es
# lo unico que no admite discusion, y aborta antes de gastar horas.
if ! .venv-gpu/bin/python scripts/verificar_bbox.py >> "$LOG" 2>&1; then
  say "*** BBOX NO COINCIDE con lo que barrio v7: abortando ***"
  exit 2
fi
say "bbox verificados contra el barrido de v7"
for B in lugo coruna ourense pontevedra; do
  case "$B" in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
  esac
  OUT="data/sweep_val_${B}_v13.tsv"
  REF="data/sweep_val_${B}_v7.tsv"
  ESPERADAS=$( [ -f "$REF" ] && wc -l < "$REF" || echo 0 )
  TENGO=$( [ -f "$OUT" ] && wc -l < "$OUT" || echo 0 )
  if [ "$ESPERADAS" -gt 100 ] && [ "$TENGO" -ge $((ESPERADAS * 97 / 100)) ]; then
    say "SALTO $B: completo ($TENGO de $ESPERADAS)"
    continue
  fi
  [ "$TENGO" -gt 0 ] && say "$B incompleto: $TENGO de $ESPERADAS, reanuda"
  say "=== barrido $B ==="
  CASTROS_VRAM_FRAC=0.45 scripts/lanzar.sh "barrido-$B-v13" 6000M \
    .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir "data/external/lidar-val-$B" --checkpoint data/cls-v13/best.pt \
    --out "$OUT" --bbox $BB \
    --workers 1 --batch 12 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
  say "barrido $B rc=$?  filas=$(wc -l < "$OUT" 2>/dev/null || echo 0)"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred "$OUT" --truth "data/${B}_fus_truth_limpia.tsv" \
    --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
done
say "### barridos de v13 terminados ###"
