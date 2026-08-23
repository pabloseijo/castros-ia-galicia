#!/bin/bash
# Orquestador de la fase 3 de Castros IA. Idempotente y reanudable.
#
# ## Por que existe
#
# La cadena anterior era un bucle largo lanzado a mano con `setsid`: no sobrevive
# a un reinicio, no avisa cuando termina, y el 2026-08-18 acabo a las 08:14 y el
# servidor estuvo dia y medio parado. Esto lo arregla: cron lo llama cada 15
# minutos y cada llamada **hace la siguiente tanda pendiente o no hace nada**.
#
# ## Como decide
#
# La verdad esta en el disco, no en una variable: la siguiente orden pendiente es
# la primera de 1..18 que no este COMPLETA. Se puede matar en cualquier momento y
# retoma solo.
#
# ## Que cuenta como COMPLETA  (corregido el 2026-08-19)
#
# La primera version daba una orden por hecha si su TSV de fusion tenia mas de
# una linea. **Eso es el fallo de v9 automatizado**: aquel barrido murio con el
# 44% de las celdas, dejo un fichero que parecia valido, y su F1 se dio por bueno
# durante nueve dias. Un fichero a medias engana.
#
# El criterio de ahora exige las tres cosas:
#   1. los CUATRO barridos por modelo (v7, v7last, v8, v12) existen;
#   2. los cuatro tienen EL MISMO numero de filas —barren la misma rejilla, asi
#      que discrepar significa que alguno murio a mitad—;
#   3. la fusion tiene 101 lineas (top-100 + cabecera), que es lo que fija
#      `data/CHECKPOINT-CONGELADO` con K=100.

set -u
cd "$HOME/castros" || exit 1

LOCK=/tmp/castros-orquestador.lock
LOG=logs/orquestador.log
ESTADO_LOCAL=data/estado-fase3.json
ESTADO_WEB=/srv/homelab/yggdrasil/www/castros.json
ULTIMA_ORDEN=18
MIN_DISCO_GB=60
MIN_RAM_MB=2000
MODELOS="v7 v7last v8 v12"

say(){ echo "[$(date '+%Y-%m-%d %H:%M')] $*" >> "$LOG"; }

# --- exclusion mutua ---
exec 9>"$LOCK"
flock -n 9 || exit 0

# --- convivencia con lo lanzado a mano ---
# El patron exige el interprete delante a proposito: `pgrep -f noche_portugal`
# se encontraba a si mismo cuando el script se escribia con heredoc dentro de
# `bash -c`, y la espera no terminaba nunca.
if pgrep -f "bash .*scripts/noche_portugal.sh" >/dev/null \
   || pgrep -f "bin/python.*cdd_portugal_download" >/dev/null \
   || pgrep -f "python.*sweep_grid_lidar.py --laz-dir data/entrada-portugal" >/dev/null; then
  exit 0
fi

# --- guardas de recursos ---
LIBRE_GB=$(df --output=avail -BG / | tail -1 | tr -dc 0-9)
RAM_MB=$(free -m | awk '/^Mem:/{print $7}')
if [ "${LIBRE_GB:-0}" -lt "$MIN_DISCO_GB" ]; then
  say "PARO: solo ${LIBRE_GB}G libres (minimo ${MIN_DISCO_GB}G)"; exit 0
fi
if [ "${RAM_MB:-0}" -lt "$MIN_RAM_MB" ]; then
  say "espero: solo ${RAM_MB}MB de RAM disponible"; exit 0
fi

# --- ¿esta COMPLETA la orden N? ---
completa(){
  local n="$1" filas="" f
  for m in $MODELOS; do
    f="data/sweep_test_portugal_${n}_${m}.tsv"
    [ -f "$f" ] || return 1
    local c; c=$(wc -l < "$f")
    [ "$c" -gt 1 ] || return 1
    if [ -z "$filas" ]; then filas="$c"
    elif [ "$c" -ne "$filas" ]; then
      say "    orden $n INCOMPLETA: $m tiene $c filas y otro $filas (algun barrido murio a mitad)"
      return 1
    fi
  done
  local fus="data/sweep_test_portugal_${n}.tsv"
  [ -f "$fus" ] || return 1
  [ "$(wc -l < "$fus")" -eq 101 ] || return 1
  return 0
}

SIGUIENTE=0
HECHAS=0
for N in $(seq 1 "$ULTIMA_ORDEN"); do
  if completa "$N"; then
    HECHAS=$((HECHAS+1))
  elif [ "$SIGUIENTE" -eq 0 ]; then
    SIGUIENTE=$N
  fi
done

# --- castros cubiertos: se cuentan de las ordenes COMPLETAS, no del plan ---
# La primera version leia la columna `acumulado` del plan, que dice cuantos
# castros DEBERIA cubrir la orden N. Si una orden falla, eso miente.
castros_cubiertos(){
  local tot=0 n
  for n in $(seq 1 "$ULTIMA_ORDEN"); do
    if completa "$n"; then
      local c; c=$(awk -F'\t' -v k="$n" 'NR>1 && $1==k {print $2}' data/plan-descarga-portugal.tsv)
      tot=$((tot + ${c:-0}))
    fi
  done
  echo "$tot"
}

escribir_estado(){
  local castros; castros=$(castros_cubiertos)
  # `precinto_roto` solo detecta la ruptura REGISTRADA en el libro de cuentas.
  # No puede detectar un cruce accidental contra la verdad hecho desde un
  # cuaderno con pandas: eso no deja rastro. El nombre del campo lo dice.
  local roto=false
  [ -s data/PRECINTO-TEST.md ] && grep -q 'romper-precinto' data/PRECINTO-TEST.md && roto=true
  {
    echo "{"
    echo "  \"actualizado\": \"$(date -Iseconds)\","
    echo "  \"fase\": \"3 - barrido del precinto portugues\","
    echo "  \"ordenes_completas\": $HECHAS,"
    echo "  \"ordenes_objetivo\": $ULTIMA_ORDEN,"
    echo "  \"castros_cubiertos\": $castros,"
    echo "  \"castros_precinto\": 282,"
    echo "  \"cobertura_pct\": $(( castros * 100 / 282 )),"
    echo "  \"trabajando_en\": \"${1:-nada}\","
    echo "  \"disco_libre_gb\": ${LIBRE_GB:-0},"
    echo "  \"precinto_roto_registrado\": $roto,"
    echo "  \"aviso\": \"precinto_roto_registrado solo ve el libro de cuentas; un cruce con pandas no deja rastro\""
    echo "}"
  } > "$ESTADO_LOCAL"
  cp -f "$ESTADO_LOCAL" "$ESTADO_WEB" 2>/dev/null || true
}

if [ "$SIGUIENTE" -eq 0 ]; then
  escribir_estado "terminado"
  if [ ! -f data/.fase3-completa ]; then
    say "=== FASE 3 COMPLETA: las $ULTIMA_ORDEN ordenes estan barridas ==="
    say "    El precinto sigue sin romperse: eso lo hace una persona."
    touch data/.fase3-completa
  fi
  exit 0
fi

escribir_estado "orden $SIGUIENTE"
say "--- orden $SIGUIENTE (completas: $HECHAS/$ULTIMA_ORDEN) ---"

# --- descarga, si falta ---
ESPERADOS=$(awk -F'\t' -v n="$SIGUIENTE" '$1==n && $2=="LAZ"' data/cdd-portugal-assets-full.tsv 2>/dev/null | wc -l)
TENGO=$(ls "data/entrada-portugal/$SIGUIENTE/LAZ" 2>/dev/null | wc -l)
if [ "$TENGO" -lt "$ESPERADOS" ] || [ "$TENGO" -eq 0 ]; then
  say "    descargando ($TENGO de $ESPERADOS teselas)"
  if ! ./scripts/cdd_portugal_download.py --orders "$SIGUIENTE" --collections LAZ --workers 4 \
       >> "logs/cdd_download_order${SIGUIENTE}.log" 2>&1; then
    say "    *** la descarga fallo (rc=$?); no se barre con datos incompletos ***"
    escribir_estado "nada"; exit 0
  fi
  say "    descarga OK ($(du -sh "data/entrada-portugal/$SIGUIENTE" 2>/dev/null | cut -f1))"
fi

# --- barrido e ingesta, con el rc COMPROBADO ---
say "    ingiriendo"
if ./scripts/ingerir_portugal.sh >> logs/ingerir_portugal.log 2>&1; then
  RC=0
else
  RC=$?
fi
if completa "$SIGUIENTE"; then
  say "    orden $SIGUIENTE COMPLETA (rc=$RC)"
else
  say "    *** orden $SIGUIENTE quedo INCOMPLETA (rc=$RC): se reintentara en la proxima llamada ***"
fi
escribir_estado "nada"
