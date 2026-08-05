#!/bin/bash
# Reanuda el barrido si el OOM killer se lo lleva. Cuarta vez que pasa en este
# proyecto, y siempre igual: muere el padre —el proceso que lleva dos horas— y
# los obreros quedan huerfanos y vivos, de modo que `pgrep` sigue encontrando
# algo y quien espere al barrido espera para siempre.
#
# Por eso el vigilante no mira `pgrep` a secas: comprueba que el fichero de
# salida **siga creciendo**. Un barrido con obreros zombis no escribe.
#
# Baja un obrero en cada reintento. Si con uno solo tampoco cabe, el problema no
# es la concurrencia y hay que arreglar `cortar_grupo`, no seguir reintentando.
set -u
cd "$HOME/castros" || exit 1
SALIDA=data/sweep_trasancos_v4.tsv
LOG=logs/vigilante_barrido.log
OBJETIVO=9290
say() { echo "[$(date +%F' '%H:%M)] $*" >> "$LOG"; }

say "=== vigilante en marcha, objetivo $OBJETIVO celdas ==="
for INTENTO in 1 2 3 4; do
  OBREROS=$((3 - INTENTO))
  [ $OBREROS -lt 1 ] && OBREROS=1
  ESTANCADO=0
  ANTES=$(wc -l < "$SALIDA" 2>/dev/null || echo 0)

  while true; do
    sleep 180
    AHORA=$(wc -l < "$SALIDA" 2>/dev/null || echo 0)
    if [ "$AHORA" -ge "$OBJETIVO" ]; then
      say "COMPLETO: $AHORA celdas"; exit 0
    fi
    if [ "$AHORA" -gt "$ANTES" ]; then
      ESTANCADO=0; ANTES=$AHORA
    else
      ESTANCADO=$((ESTANCADO + 1))
      say "sin avance ($AHORA celdas), aviso $ESTANCADO/2"
      [ $ESTANCADO -ge 2 ] && break
    fi
  done

  say "estancado en $ANTES; limpiando huerfanos y reanudando con $OBREROS obreros"
  for PID in $(pgrep -f "sweep_grid_lidar.py"); do
    CMD=$(tr "\0" " " < /proc/$PID/cmdline 2>/dev/null)
    case "$CMD" in
      *bash*) : ;;                       # nunca matar un shell por el patron
      *sweep_grid_lidar.py*) kill -TERM "$PID" 2>/dev/null ;;
    esac
  done
  sleep 8
  nohup setsid .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-trasancos-v1 \
    --checkpoint data/cls-v4/best.pt --out "$SALIDA" \
    --bbox -8.3538 43.3990 -8.0078 43.6688 --workers $OBREROS --batch 16 \
    >> logs/barrido_v4_reanudado.log 2>&1 < /dev/null &
  say "reanudado (intento $INTENTO, $OBREROS obreros)"
done
say "AGOTADOS los reintentos en $(wc -l < "$SALIDA") celdas: no es concurrencia, es cortar_grupo"
