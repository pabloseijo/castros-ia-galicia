#!/bin/sh
# Lanza un trabajo con TECHO DE MEMORIA propio, usando cgroups v2.
#
# El 2026-08-08 el OOM killer se llevo DOS trabajos largos —cuatro horas de
# barrido de v8 y el de v9— porque el kernel mata al proceso con mayor
# `oom_score`, que suele ser el que mas memoria acumulo, o sea **el que llevaba
# mas tiempo trabajando**. El recien llegado que provoco la presion sobrevive.
#
# Con `systemd-run --user --scope -p MemoryMax=` cada trabajo vive en su propio
# cgroup: si SE PASA de su presupuesto, muere EL, y los demas ni se enteran.
# Invierte quien paga el exceso, que es lo correcto.
#
# `MemoryHigh` (aviso: ralentiza y fuerza recuperacion) va al 85% de
# `MemoryMax` (limite duro) para que el trabajo tenga ocasion de soltar memoria
# antes de que lo maten.
#
# Uso:
#   scripts/lanzar.sh <nombre> <memMax> <orden...>
#   scripts/lanzar.sh barrido-v10 3G .venv-gpu/bin/python scripts/sweep_grid_lidar.py ...
set -u
[ $# -lt 3 ] && { echo "uso: $0 <nombre> <memMax: 3G|500M> <orden...>"; exit 2; }
NOMBRE=$1; MEM=$2; shift 2

# 85% de MemoryMax, respetando la unidad. Hacerlo con `sed 's/G$//'` fallaba con
# «200M»: awk leia «200M*0.85» como concatenacion y salia MemoryHigh=2000G, o
# sea sin aviso ninguno. Un limite mal calculado que no protege es peor que no
# ponerlo, porque da falsa seguridad.
NUM=$(printf '%s' "$MEM" | tr -cd '0-9.')
UNI=$(printf '%s' "$MEM" | tr -cd 'KMGTkmgt')
[ -z "$NUM" ] && { echo "memoria no valida: $MEM"; exit 2; }
HIGH=$(awk -v n="$NUM" -v u="$UNI" 'BEGIN{printf "%.0f%s", n*0.85, u}')

echo "[$(date +%H:%M)] '$NOMBRE': MemoryMax=$MEM MemoryHigh=$HIGH"
exec systemd-run --user --scope --collect \
  --unit="castros-$NOMBRE" \
  -p MemoryMax="$MEM" -p MemoryHigh="$HIGH" -p MemorySwapMax=0 \
  -- "$@"
