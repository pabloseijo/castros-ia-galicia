#!/bin/sh
# Barre las provincias gallegas ya cacheadas con la CONFIGURACION CONGELADA.
#
# ## Por que existe
#
# La GPU llevaba dias al 0% porque el cuello de botella era la descarga, no el
# computo. Pero habia `2.402` teselas ya convertidas a `.npz` de las cuatro
# provincias, y **Galicia nunca se ha barrido con la configuracion congelada**:
# los barridos que hay (`sweep_*_ens_geom`, `ens_max`, `ens_media`) son de
# ensembles anteriores al congelado del 2026-08-11.
#
# Y barrer Galicia entera con esa configuracion **es el entregable del proyecto**.
#
# ## Que es la configuracion congelada
#
#   fusion por rango (RRF) de v7 + v7last + v8 + v12, con k = 60
#   enlace 512 m · tolerancia 500 m · sin criba de falsos positivos
#   7 canales con --dem-dir activo
#   diezmado de densidad: SOLO en Portugal, aqui NO
#
# ## Por que se puede barrer Galicia sin romper nada
#
# Galicia es `train` + `validation`. El precinto es el norte de Portugal, y no se
# toca aqui. Lo que NO se puede hacer es **ajustar** nada contra estos
# resultados: la configuracion ya esta congelada y se aplica tal cual.
#
# ## Convivencia
#
# Se lanza con VRAM limitada y un solo worker, como el barrido de Portugal, para
# que la descarga del precinto siga por red sin competir. Son recursos distintos
# —GPU contra red— y esa es justamente la razon de lanzarlo ahora.
set -u

cd "$HOME/castros" || exit 1
LOG=logs/barrido_galicia_congelada.log
say(){ echo "[$(date '+%Y-%m-%d %H:%M')] $*" >> "$LOG"; }

MODELOS="v7:data/cls-v7/best.pt v7last:data/cls-v7/last.pt v8:data/cls-v8/best.pt v12:data/cls-v12/best.pt"

# Guarda de memoria: 8 GB en la maquina y hay descargas vivas. Si no hay sitio,
# se espera a la proxima llamada en vez de invitar al OOM killer, que se lleva
# el proceso que llevaba horas y no el que acaba de entrar.
LIBRE=$(free -m | awk '/^Mem:/{print $7}')
if [ "${LIBRE:-0}" -lt 2800 ]; then   # 3 workers piden mas sitio
  say "solo ${LIBRE}M disponibles: no arranco"
  exit 0
fi

# Un solo barrido a la vez. `pgrep -f` se encuentra a si mismo, asi que se
# pregunta a la GPU, que no puede confundirse consigo misma.
GPU_PIDS=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c . || echo 0)
if [ "${GPU_PIDS:-0}" -gt 0 ]; then
  say "la GPU ya tiene $GPU_PIDS proceso(s): no arranco otro"
  exit 0
fi

for PROV in coruna lugo ourense pontevedra; do
  CACHE="data/dem-cache-$PROV"
  OUT="data/sweep_galicia_${PROV}_congelada.tsv"
  OUTFULL="data/sweep_galicia_${PROV}_congelada_full.tsv"

  [ -d "$CACHE" ] || continue
  NT=$(ls "$CACHE"/*.npz 2>/dev/null | wc -l)
  [ "$NT" -gt 0 ] || continue
  if [ -f "$OUT" ] && [ "$(wc -l < "$OUT")" -gt 1 ]; then
    say "--- $PROV ya fusionada ($(wc -l < "$OUT") filas) ---"
    continue
  fi

  # El bbox sale de los nombres de las teselas del PNOA
  # (PNOA-2024-GAL-<X_km>-<Y_km>-H29 = esquina en UTM 29N), pero
  # `sweep_grid_lidar.py` **espera el bbox en GRADOS**: lo transforma el mismo a
  # `--grid-crs`. Pasarle UTM da `OverflowError: cannot convert float infinity to
  # integer`, que no dice nada del bbox y cuesta encontrar.
  BB=$(ls "$CACHE"/*.npz | sed 's|.*/||' | .venv-gpu/bin/python -c '
import sys, re
from pyproj import Transformer
xs, ys = [], []
for ln in sys.stdin:
    m = re.match(r"PNOA-\d+-GAL-(\d+)-(\d+)-H29", ln.strip())
    if m:
        xs.append(int(m.group(1))); ys.append(int(m.group(2)))
if not xs:
    sys.exit(1)
t = Transformer.from_crs("EPSG:25829", "EPSG:4326", always_xy=True)
lo0, la0 = t.transform(min(xs)*1000, min(ys)*1000)
lo1, la1 = t.transform((max(xs)+1)*1000, (max(ys)+1)*1000)
# margen de una tesela por si la proyeccion recorta una esquina
print("%.6f %.6f %.6f %.6f" % (lo0-0.02, la0-0.02, lo1+0.02, la1+0.02))
')
  [ -n "$BB" ] || { say "*** $PROV: no pude derivar el bbox ***"; continue; }

  say "=== $PROV: $NT teselas, bbox lon/lat = $BB ==="

  PREDS=""; NAMES=""
  for MC in $MODELOS; do
    M=${MC%%:*}; CK=${MC#*:}
    PRED="data/sweep_galicia_${PROV}_${M}.tsv"
    PREDS="$PREDS $PRED"; NAMES="$NAMES $M"
    if [ -f "$PRED" ] && [ "$(wc -l < "$PRED")" -gt 1 ]; then
      say "  --- $M ya barrido ($(wc -l < "$PRED") filas) ---"
      continue
    fi
    [ -f "$CK" ] || { say "  *** falta $CK ***"; exit 1; }
    say "  --- barriendo $M sobre la cache DEM ---"
    # --laz-dir es obligatorio en el guion aunque no se use cuando hay --dem-dir;
    # se le pasa el propio directorio de cache, que existe y esta vacio de .laz.
    CASTROS_VRAM_FRAC=0.80 .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
      --laz-dir "$CACHE" --dem-dir "$CACHE" --checkpoint "$CK" \
      --out "$PRED" --bbox $BB --grid-crs EPSG:25829 \
      --workers "${BARRIDO_WORKERS:-3}" --batch 24 --chunk 200 --max-celdas-tarea 24 >> "$LOG" 2>&1
    say "  rc=$? $M filas=$(wc -l < "$PRED" 2>/dev/null || echo 0)"
  done

  # Criterio de barrido completo, el mismo que usa el orquestador: los cuatro
  # modelos tienen que dar EL MISMO numero de filas. Si no, alguno se trunco.
  FILAS=$(for P in $PREDS; do wc -l < "$P" 2>/dev/null || echo 0; done | sort -u | wc -l)
  if [ "$FILAS" -ne 1 ]; then
    say "  *** los 4 modelos no coinciden en filas: NO fusiono $PROV ***"
    continue
  fi

  say "  --- fusion RRF (k=60) ---"
  .venv-gpu/bin/python scripts/fusionar_barridos_rrf.py \
    --pred $PREDS --names $NAMES --out-full "$OUTFULL" --out-top "$OUT" \
    --top-k 100 --rrf-k 60 >> "$LOG" 2>&1
  say "  $PROV LISTA: top=$(wc -l < "$OUT" 2>/dev/null || echo 0) full=$(wc -l < "$OUTFULL" 2>/dev/null || echo 0)"
done
say "=== barrido de Galicia terminado ==="
