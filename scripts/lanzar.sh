#!/bin/sh
# Lanza un trabajo con TECHO DE MEMORIA propio, usando cgroups v2.
#
# El 2026-08-08 el OOM killer se llevo dos trabajos largos —cuatro horas de
# barrido de v8 y el de v9— porque el kernel mata al proceso con mayor
# `oom_score`, que suele ser **el que llevaba mas tiempo trabajando**. El recien
# llegado que provoco la presion sobrevive. Con un cgroup por trabajo, el que se
# pasa de su presupuesto muere EL y los demas ni se enteran.
#
# ## Dos fallos ya cometidos EN ESTE MISMO GUION
#
# El calculo de `MemoryHigh` ha fallado dos veces, y las dos de forma silenciosa:
#
# 1. Con `sed 's/G$//'` y una entrada de `200M`, awk leia `200M*0.85` como
#    concatenacion y salia `MemoryHigh=2000G`: ningun aviso.
# 2. Con `printf "%.0f"`, una entrada de `3G` daba `MemoryHigh=3G` —igual que
#    `MemoryMax`—, o sea otra vez ningun aviso. El barrido de Lugo con v10 murio
#    asi: llego al techo y lo mataron en seco, sin fase de ralentizacion, y el
#    log termina a media frase sin excepcion ninguna.
#
# Por eso ahora se convierte todo a **bytes** y se calcula en enteros: sin
# unidades que interpretar y sin redondeos que se coman el margen.
#
# La leccion que vale mas que el arreglo: **un limite mal calculado que no
# protege es peor que no ponerlo**, porque da falsa seguridad. Los dos fallos se
# cazaron probando, no leyendo.
#
# Uso:
#   scripts/lanzar.sh <nombre> <memMax> <orden...>
#   scripts/lanzar.sh barrido-lugo 6G .venv-gpu/bin/python scripts/sweep_grid_lidar.py ...
set -u
[ $# -lt 3 ] && { echo "uso: $0 <nombre> <memMax: 3G|500M> <orden...>"; exit 2; }
NOMBRE=$1; MEM=$2; shift 2

NUM=$(printf '%s' "$MEM" | tr -cd '0-9')
UNI=$(printf '%s' "$MEM" | tr -cd 'KMGTkmgt' | tr '[:lower:]' '[:upper:]')
[ -z "$NUM" ] && { echo "memoria no valida: $MEM"; exit 2; }
case "$UNI" in
  K) MUL=1024;;  M) MUL=1048576;;  G) MUL=1073741824;;  T) MUL=1099511627776;;
  "") MUL=1;;
  *) echo "unidad no reconocida en $MEM"; exit 2;;
esac
MAX=$((NUM * MUL))
HIGH=$((MAX * 85 / 100))
[ "$HIGH" -ge "$MAX" ] && { echo "ERROR: MemoryHigh >= MemoryMax, revisa el calculo"; exit 2; }

echo "[$(date +%H:%M)] '$NOMBRE': Max=$((MAX/1048576))M High=$((HIGH/1048576))M"
exec systemd-run --user --scope --collect \
  --unit="castros-$NOMBRE" \
  -p MemoryMax="$MAX" -p MemoryHigh="$HIGH" -p MemorySwapMax=0 \
  -- "$@"
