#!/bin/sh
# Sale 0 si la GPU está libre para que entre un proceso nuevo; 1 si no.
#
# Existe por lo que pasó el 2026-08-10 a las 17:51: la cadena de v9 recorrió
# los tres bloques en un minuto con `CUDA error: device is busy or unavailable`
# y dejó tres barridos a cero sin que nada lo impidiera. La causa no era del
# proyecto: **la GPU estaba entrenando un modelo de voz de Pablo**
# (`mimir_chenevert`, RVC, 6,4 de los 8 GB) y la tarjeta estaba en
# `Exclusive_Process`, que permite **un solo contexto CUDA a la vez**.
#
# La regla que sale de aquí: el trabajo de castros **hace cola**, no desaloja.
# `acaparar_nodo.py` es para tomar el nodo cuando el trabajo es nuestro; cuando
# es de otro, se espera.
#
# El criterio depende del modo de cómputo, y hay que mirarlo:
#   Exclusive_Process -> basta con que haya CUALQUIER proceso para bloquear.
#   Default           -> conviven, y lo que manda es la VRAM libre.
set -u

MODO=$(nvidia-smi --query-gpu=compute_mode --format=csv,noheader 2>/dev/null)
[ -n "$MODO" ] || exit 1        # sin nvidia-smi no se arriesga

APPS=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c .)

case "$MODO" in
  Exclusive_Process)
      [ "$APPS" -eq 0 ] || exit 1
      ;;
  *)
      # En Default se pide un margen: por debajo de esto un barrido de 7
      # canales o un entrenamiento no arrancan y mueren al primer lote.
      LIBRE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null)
      [ "${LIBRE:-0}" -ge 3500 ] || exit 1
      ;;
esac
exit 0
