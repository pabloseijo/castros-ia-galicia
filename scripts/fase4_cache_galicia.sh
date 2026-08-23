#!/bin/bash
# Fase 4: construir la cache DEM de Galicia entera, bloque a bloque.
#
# ## Por que una cache y no barrer directamente
#
# El 2026-08-17 se midio que la via de la cache encuentra LOS MISMOS castros que
# la nube (mismos TP en 4 de 5 umbrales sobre los cuatro bloques de validacion),
# y ocupa 1,9 MB por tesela contra 63 MB del LAZ. Construida una vez:
#
#   barrido de Galicia por nube   : 193 h  y 1,72 TB en disco
#   barrido de Galicia por cache  : 11,5 h y ~56-105 GB, reutilizable
#
# Rebarrer con un modelo nuevo pasa de costar una semana a costar una noche. Eso
# es lo que el consejo puso como objetivo el 2026-08-19.
#
# ## El ciclo, por bloque
#
#   bajar las teselas del bbox -> convertir a .npz -> BORRAR los LAZ -> siguiente
#
# El disco nunca tiene mas de un bloque de LAZ (~40 GB); lo que se acumula es la
# cache, que es lo que ocupa poco.
#
# ## Espera al precinto
#
# La fase 3 es la puerta y tiene prioridad: mientras haya un barrido de Portugal
# vivo, esto no arranca. El patron exige el interprete delante porque `pgrep -f`
# se encuentra a si mismo cuando el guion se escribio con heredoc.

set -u
cd "$HOME/castros" || exit 1

LOCK=/tmp/castros-fase4.lock
LOG=logs/fase4_cache_galicia.log
CACHE=data/dem-cache-galicia
TMP_LAZ=data/laz-tanda-galicia
BLOQUES=data/bloques_galicia.txt
ESTADO=data/estado-fase4.json
MIN_DISCO_GB=120        # mas alto que la fase 3: aqui una tanda son ~40 GB
CONV_WORKERS=6          # lo ajusta la guarda de abajo
MIN_RAM_MB=2500

say(){ echo "[$(date '+%Y-%m-%d %H:%M')] $*" >> "$LOG"; }

exec 9>"$LOCK"
flock -n 9 || exit 0

# --- pausa explicita ---
# Cron llama cada 30 min, asi que matar el proceso no sirve de nada. Este
# fichero es la forma de decirle que ceda sin tocar el crontab.
if [ -f data/.fase4-en-pausa ]; then
  exit 0
fi

# --- la fase 3 manda ---
# La fase 4 ya NO se aparta cuando Portugal barre: son recursos distintos —el
# barrido usa GPU, la conversion usa CPU— y esperar deja la maquina a medio
# gas. En vez de cederle el sitio, se hace pequena.
#
# La guarda no desaparece porque el riesgo de esta maquina no es la CPU: son
# los 8 GB. Dos barridos juntos dejaron 167 MB libres y 2,9 GB de swap el
# 2026-08-19, y el triaje morfologico murio por OOM en 5 de 13 ordenes.
# Se le pregunta a la GPU, no al listado de procesos: `pgrep -f` da falsos
# positivos cuando un ancestro lleva el patron en su cmdline —una sesion SSH
# que lo mencione basta— y eso ya costo tres diagnosticos equivocados.
# nvidia-smi devuelve quien tiene contexto abierto en la GPU y no puede
# confundirse consigo mismo. El pgrep queda de respaldo por si nvidia-smi
# falla o el barrido corriera en CPU.
GPU_OCUPADA=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c . || echo 0)
if [ "${GPU_OCUPADA:-0}" -gt 0 ] \
   || pgrep -f "python.*sweep_grid_lidar.py --laz-dir data/entrada-portugal" >/dev/null; then
  CONV_WORKERS=2
  MIN_RAM_MB=3000        # mas exigente: hay un barrido comiendo memoria
  say "    (Portugal esta barriendo: 2 obreros y umbral de RAM alto)"
else
  CONV_WORKERS=6
  MIN_RAM_MB=2500
fi

# --- ¿ha terminado la fase 3? ---
COMPLETAS=0
for N in $(seq 1 18); do
  ok=1; filas=""
  for m in v7 v7last v8 v12; do
    f="data/sweep_test_portugal_${N}_${m}.tsv"
    [ -f "$f" ] || { ok=0; break; }
    c=$(wc -l < "$f"); [ "$c" -gt 1 ] || { ok=0; break; }
    if [ -z "$filas" ]; then filas="$c"; elif [ "$c" -ne "$filas" ]; then ok=0; break; fi
  done
  fus="data/sweep_test_portugal_${N}.tsv"
  [ "$ok" -eq 1 ] && [ -f "$fus" ] && [ "$(wc -l < "$fus")" -eq 101 ] && COMPLETAS=$((COMPLETAS+1))
done
if [ "$COMPLETAS" -lt 18 ]; then
  exit 0   # sin ruido: la fase 3 sigue y esto espera su turno
fi

# --- guardas ---
LIBRE_GB=$(df --output=avail -BG / | tail -1 | tr -dc 0-9)
RAM_MB=$(free -m | awk '/^Mem:/{print $7}')
if [ "${LIBRE_GB:-0}" -lt "$MIN_DISCO_GB" ]; then
  say "PARO: ${LIBRE_GB}G libres, hacen falta ${MIN_DISCO_GB}G para una tanda"; exit 0
fi
[ "${RAM_MB:-0}" -lt "$MIN_RAM_MB" ] && exit 0

mkdir -p "$CACHE" "$TMP_LAZ"

# --- siguiente bloque sin cache ---
# Reanudable por marca en disco: un bloque terminado deja su .hecho
SIG=""; W=""; S=""; E=""; N2=""; HECHOS=0; TOTAL=0
while read -r NOM w s e n; do
  case "$NOM" in \#*|"") continue ;; esac
  TOTAL=$((TOTAL+1))
  if [ -f "$CACHE/.hecho-$NOM" ]; then HECHOS=$((HECHOS+1)); continue; fi
  if [ -z "$SIG" ]; then SIG="$NOM"; W="$w"; S="$s"; E="$e"; N2="$n"; fi
done < "$BLOQUES"

NPZ=$(ls "$CACHE"/*.npz 2>/dev/null | wc -l)
GB=$(du -sBG "$CACHE" 2>/dev/null | cut -f1 | tr -dc 0-9)
{
  echo "{"
  echo "  \"actualizado\": \"$(date -Iseconds)\","
  echo "  \"fase\": \"4 - cache DEM de Galicia\","
  echo "  \"bloques_hechos\": $HECHOS,"
  echo "  \"bloques_total\": $TOTAL,"
  echo "  \"teselas_en_cache\": $NPZ,"
  echo "  \"cache_gb\": ${GB:-0},"
  echo "  \"trabajando_en\": \"${SIG:-nada}\","
  echo "  \"disco_libre_gb\": ${LIBRE_GB:-0}"
  echo "}"
} > "$ESTADO"
cp -f "$ESTADO" /srv/homelab/yggdrasil/www/castros-fase4.json 2>/dev/null || true

if [ -z "$SIG" ]; then
  if [ ! -f "$CACHE/.completa" ]; then
    say "=== CACHE DE GALICIA COMPLETA: $HECHOS bloques, $NPZ teselas, ${GB}G ==="
    say "    Barrer Galicia entera cuesta ahora ~11,5 h con --dem-dir $CACHE"
    touch "$CACHE/.completa"
  fi
  exit 0
fi

say "--- bloque $SIG ($((HECHOS+1)) de $TOTAL) bbox=$W $S $E $N2 ---"
rm -rf "${TMP_LAZ:?}/$SIG"; mkdir -p "$TMP_LAZ/$SIG"

if ! .venv-gpu/bin/python scripts/download_trasancos_lidar.py --bbox "$W" "$S" "$E" "$N2" \
     --laz-dir "$TMP_LAZ/$SIG" --out-dir "$TMP_LAZ/$SIG" \
     --workers 4 --min-free-gb "$MIN_DISCO_GB" >> "$LOG" 2>&1; then
  say "    descarga fallo; se reintenta en la proxima llamada"
  exit 0
fi
NL=$(find "$TMP_LAZ/$SIG" -name '*.laz' | wc -l)
say "    bajadas $NL teselas ($(du -sh "$TMP_LAZ/$SIG" 2>/dev/null | cut -f1))"
if [ "$NL" -eq 0 ]; then
  say "    bloque sin teselas del PNOA (mar o fuera de cobertura): marcado y seguimos"
  touch "$CACHE/.hecho-$SIG"; exit 0
fi

# --borrar-laz: el LAZ se tira en cuanto su .npz esta escrito
if .venv-gpu/bin/python scripts/laz_a_dem.py --laz-dir "$TMP_LAZ/$SIG" --out "$CACHE" \
     --workers "$CONV_WORKERS" --borrar-laz >> "$LOG" 2>&1; then
  touch "$CACHE/.hecho-$SIG"
  say "    cache OK | teselas totales: $(ls "$CACHE"/*.npz 2>/dev/null | wc -l) | $(du -sh "$CACHE" | cut -f1)"
else
  say "    *** la conversion fallo; el bloque NO se marca y se reintentara ***"
fi
rm -rf "${TMP_LAZ:?}/$SIG"
