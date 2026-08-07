#!/bin/sh
# Triaje de los candidatos de los cuatro bloques de validacion.
#
# Existe como fichero del repo y no como comando suelto por un motivo concreto:
# el 2026-08-07 el triaje se lanzo desde `/tmp`, los ficheros de candidatos se
# regeneraron **a mitad de ejecucion** con el arreglo del desborde de recuadro,
# y las salidas quedaron mezcladas: Lugo entrego `8` filas cuando su entrada
# tenia `5`, y las tres de mas eran castros ya catalogados —uno a `22 m` del
# Castro da Igrexa/Castro de Lebruxo— colocados en el tercer puesto de la lista.
#
# La comprobacion de abajo es lo unico que lo habria cazado en el momento: si
# salen mas filas de las que entran, la salida es de otra ejecucion.
#
# Uso:  scripts/run_triaje.sh [directorio-de-salida]
set -u
cd "$(dirname "$0")/.." || exit 1
OUT="${1:-data/triaje-v7b}"
PY=.venv-gpu/bin/python
[ -x "$PY" ] || PY=python3
mkdir -p "$OUT"
fallos=0

for B in lugo coruna ourense pontevedra; do
  ENT="data/candidatos_${B}_v7.tsv"
  [ -f "$ENT" ] || { echo "######## $B ######## SIN FICHERO DE ENTRADA"; continue; }
  N=$(( $(wc -l < "$ENT") - 1 ))
  echo "######## $B ######## entrada: $N candidatos"
  nice -n 5 "$PY" scripts/verificar_candidatos.py \
    --candidatos "$ENT" \
    --laz-dir "data/external/lidar-val-$B" \
    --calibrar-con "data/${B}_fus_truth_limpia.tsv" \
    --out "$OUT"
  SAL="$OUT/candidatos_${B}_v7_triaje.csv"
  if [ ! -f "$SAL" ]; then
    echo "*** $B: no se escribio la salida ***"; fallos=$((fallos+1)); continue
  fi
  M=$(( $(wc -l < "$SAL") - 1 ))
  echo "COMPROBACION $B: entraron $N, salieron $M"
  if [ "$N" -ne "$M" ]; then
    echo "*** DESCUADRE EN $B: la salida no corresponde a esta entrada ***"
    fallos=$((fallos+1))
  fi
done

if [ "$fallos" -ne 0 ]; then
  echo "### triaje terminado CON $fallos BLOQUES EN FALLO ###"; exit 1
fi
echo "### triaje completo, los cuatro bloques cuadran ###"
