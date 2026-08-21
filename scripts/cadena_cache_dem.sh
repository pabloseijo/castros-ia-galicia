#!/bin/sh
# Construye la caché de DEM de los bloques que no la tienen.
#
# `--dem-dir` se desbloqueó el 2026-08-11 al descubrir que el desacuerdo con la
# vía del `.laz` era **imprecisión del barrido**, no de la caché: un
# `astype(float32)` sobre coordenadas UTM movía el 3,13% de los puntos de celda.
# Verificado en dos bloques tras el arreglo: correlación 1,000000 en Lugo y
# 0,9999 en Pontevedra, diferencia absoluta 0,0000.
#
# Lo que vale: descomprimir LAZ es el 87,6% del coste de un barrido y se hacía
# 8,4 veces por tesela. Con caché, una. Los ~12 barridos que quedan en cola
# pasan de unas 30 horas a unas 4.
#
# Ya existen las de lugo y pontevedra. Faltan coruna y ourense.
#
# Es trabajo de CPU y disco, así que espera a que no haya barrido en marcha
# para no pelearse con él por los mismos ficheros.
set -u
cd "$(dirname "$0")/.." || exit 1
LOG=logs/cadena_cache_dem.log
say() { echo "[$(date +%F\ %H:%M)] $*" | tee -a "$LOG"; }

say "esperando a que no haya barridos en marcha"
while pgrep -f "scripts/sweep_grid_lidar.py" > /dev/null; do sleep 300; done
say "sin barridos: empieza la construccion de caches"

for B in ourense coruna; do
  DST="data/dem-cache-$B"
  SRC="data/external/lidar-val-$B"
  N_LAZ=$(ls "$SRC"/*.laz 2>/dev/null | wc -l)
  N_DEM=$(ls "$DST"/*.npz 2>/dev/null | wc -l)
  if [ "$N_DEM" -ge "$N_LAZ" ] && [ "$N_LAZ" -gt 0 ]; then
    say "$B ya tiene cache completa ($N_DEM de $N_LAZ)"
    continue
  fi
  say "=== cache de $B: $N_DEM de $N_LAZ hechas ==="
  # `laz_a_dem.py` es reanudable: no rehace lo que ya existe.
  nice -n 19 .venv-gpu/bin/python scripts/laz_a_dem.py \
    --laz-dir "$SRC" --out "$DST" --res-m 1.0 --workers 4 >> "$LOG" 2>&1
  # `--workers 4` de los 12 nucleos: convive con lo que haya. Y NO se usa
  # `--borrar-laz` aunque liberaria 40 GB por bloque: es irreversible y
  # volver a bajar el PNOA cuesta horas. Esa decision no es mia.
  say "$B rc=$?  ahora $(ls "$DST"/*.npz 2>/dev/null | wc -l) de $N_LAZ"

  say "--- verificando equivalencia en $B ---"
  nice -n 19 .venv-gpu/bin/python scripts/verificar_dem.py \
    --laz-dir "$SRC" --dem-dir "$DST" --n 20 >> "$LOG" 2>&1
done

say "### caches de DEM terminadas ###"
