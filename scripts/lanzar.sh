#!/bin/sh
# Lanza un trabajo con TECHO DE MEMORIA propio, usando cgroups v2.
#
# El 2026-08-08 el OOM killer se llevo dos trabajos largos —cuatro horas de
# barrido de v8 y el de v9— porque el kernel mata al proceso con mayor
# `oom_score`, que suele ser **el que llevaba mas tiempo trabajando**. El recien
# llegado que provoco la presion sobrevive. Con un cgroup por trabajo, el que se
# pasa de su presupuesto muere EL y los demas ni se enteran.
#
# ## TRES fallos ya cometidos EN ESTE MISMO GUION
#
# El calculo de `MemoryHigh` ha fallado tres veces, y las tres en silencio:
#
# 1. Con `sed 's/G$//'` y una entrada de `200M`, awk leia `200M*0.85` como
#    concatenacion y salia `MemoryHigh=2000G`: ningun aviso.
# 2. Con `printf "%.0f"`, una entrada de `3G` daba `MemoryHigh=3G` —igual que
#    `MemoryMax`—, o sea otra vez ningun aviso. El barrido de Lugo con v10 murio
#    asi: llego al techo y lo mataron en seco, sin fase de ralentizacion, y el
#    log termina a media frase sin excepcion ninguna.
#
# 3. Puesto al `85%` de `MemoryMax`, **estrangulo el corte del corpus de v11p**.
#    `MemoryHigh` no es un aviso: es un ACELERADOR AL REVES. Cuando el cgroup lo
#    supera, el kernel duerme a sus procesos con retardo creciente para forzar
#    reclamo. Un trabajo cuyo conjunto de trabajo vive de forma natural por encima
#    del `85%` de su techo se queda ahi para siempre: el obrero aparecio con
#    `3 h` de CPU, en `mem_cgroup_handle_over_high`, y `26` minutos sin escribir un
#    solo fichero. **No murio: se paralizo**, que es el peor de los dos mundos
#    porque desde fuera parece que sigue trabajando.
#
# Por eso ahora se convierte todo a **bytes**, se calcula en enteros —sin unidades
# que interpretar ni redondeos que se coman el margen— y `MemoryHigh` va al
# **`95%`**, no al `85%`: solo debe actuar en el ultimo tramo antes del limite
# duro. Para un trabajo por lotes es preferible morir y reintentar con mas techo
# que arrastrarse indefinidamente sin que nadie se entere.
#
# **La leccion de fondo, que es sobre mi.** Este guion se escribio para proteger
# trabajos largos y hoy ha matado uno y paralizado otro. Una capa de seguridad
# anadida deprisa es una superficie de fallo nueva, y encima de las silenciosas:
# los tres fallos se manifestaron como «el trabajo va raro», nunca como un error.
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
HIGH=$((MAX * 95 / 100))
[ "$HIGH" -ge "$MAX" ] && { echo "ERROR: MemoryHigh >= MemoryMax, revisa el calculo"; exit 2; }

echo "[$(date +%H:%M)] '$NOMBRE': Max=$((MAX/1048576))M High=$((HIGH/1048576))M"
exec systemd-run --user --scope --collect \
  --unit="castros-$NOMBRE" \
  -p MemoryMax="$MAX" -p MemoryHigh="$HIGH" -p MemorySwapMax=0 \
  -- "$@"
