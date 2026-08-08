#!/bin/sh
# Encola los barridos de v9 que faltan, UNO detras de otro y sin duplicar.
#
# El 2026-08-08 se lanzaron los tres a la vez y murieron dos: A Coruna con
# `CUDA out of memory` y Ourense con `BrokenProcessPool` —el OOM killer se llevo
# un obrero—. La causa no es un fallo del codigo: el nodo tiene `8 GB` y
# entrenamiento (`3 GB`) mas tres barridos (`~1 GB` cada uno con sus obreros) no
# caben. Estaba sobresuscribiendo la maquina.
#
# **La guarda de duplicado no es opcional.** La primera version de esta cola
# habria barrido Pontevedra por segunda vez: la cadena vieja habia seguido con
# ese bloque por su cuenta tras fallar Ourense, y yo no lo mire antes de encolar.
# Dos barridos del mismo bloque escribiendo el mismo TSV es trabajo perdido y,
# peor, salida corrupta.
#
# Se espera **por PID**, no con `pgrep -f patron`: un patron se encuentra a si
# mismo en la linea de comandos del propio guion. En esta misma sesion `pgrep`
# volvio a autoencontrarse tres veces, incluida una comprobacion de esta cola.
set -u
ANTERIOR=${1:-0}
LOG=logs/cola_v9.log
say() { echo "[$(date +%H:%M)] $*" >> "$LOG"; }

# ¿hay ya un barrido de este bloque en marcha? Se mira `/proc/PID/cmdline`
# directamente, que es la unica forma de no contarse a si mismo.
corriendo() {
  for d in /proc/[0-9]*; do
    p=${d#/proc/}
    [ "$p" = "$$" ] && continue
    c=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null) || continue
    case "$c" in
      *sweep_grid_lidar.py*lidar-val-$1*) return 0;;
    esac
  done
  return 1
}

if [ "$ANTERIOR" -gt 0 ]; then
  say "esperando al PID $ANTERIOR"
  while [ -d "/proc/$ANTERIOR" ]; do sleep 60; done
  say "PID $ANTERIOR ha terminado"
fi

for B in ourense pontevedra; do
  if corriendo "$B"; then
    say "SALTO $B: ya hay un barrido suyo en marcha"
    continue
  fi
  N=$(wc -l < "data/sweep_val_${B}_v9.tsv" 2>/dev/null || echo 0)
  if [ "$N" -gt 100 ]; then
    say "SALTO $B: ya tiene $N filas barridas"
    continue
  fi
  say "=== barrido $B con v9 ==="
  CASTROS_VRAM_FRAC=0.15 scripts/lanzar.sh "barrido-$B-v9" 2500M \
    .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir "data/external/lidar-val-$B" --checkpoint data/cls-v9/best.pt \
    --out "data/sweep_val_${B}_v9.tsv" \
    --bbox $([ "$B" = ourense ] && echo "-8.25 42.25 -8.00 42.50" \
                                || echo "-8.75 42.25 -8.50 42.50") \
    --ortofoto-dir data/ortofotos-rejilla --ortofoto-prefijo "${B}_" \
    --workers 2 --batch 12 --chunk 100 --max-celdas-tarea 30 >> "$LOG" 2>&1
  say "barrido $B rc=$?"
done
say "cola terminada"
