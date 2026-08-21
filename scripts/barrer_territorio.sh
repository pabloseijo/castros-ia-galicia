#!/bin/sh
# Barre un territorio entero por tandas, sin que el LiDAR quepa nunca de golpe.
#
# ## El problema que resuelve
#
# Barrer Galicia y el norte de Portugal exige `50.852` teselas de `1 km²` a
# `63 MB` = **`2,96 TB`**, contra `221 GB` libres. No cabe por un factor de trece.
#
# La via del DEM cacheado —que ocupa `72x` menos— habria resuelto esto, pero esta
# **refutada**: el modelo cambia sus puntuaciones al cortarse desde el raster.
#
# Asi que se hace por tandas: **bajar las teselas de un bloque, barrerlo, borrar
# las teselas, siguiente**. En disco nunca hay mas de un bloque —`638` teselas,
# `~40 GB`—, y el resultado que se conserva es el TSV de puntuaciones, que pesa
# unos `500 KB` por bloque.
#
# ## Lo que NO hace, a proposito
#
# No borra nada que estuviera antes: los directorios de validacion
# (`lidar-val-*`) y los positivos (`lidar-positives-v1`) se dejan intactos. Solo
# limpia lo que el mismo ha bajado, y solo si `--borrar` esta puesto.
#
# Es **reanudable**: un bloque cuyo TSV ya tiene filas suficientes se salta sin
# bajar nada.
#
# **La salida de `curl` se filtra.** Sin eso, el progreso de la descarga —barras,
# velocidades, tiempos— ahoga el log: en la descarga grande del 2026-08-08 dejo
# el fichero ilegible y hubo que ir al `journal` para saber si algo habia fallado.
# Un log que no se puede leer es un log que no se lee.
set -u

MODELO=${MODELO:-v7}
CKPT=${CKPT:-data/cls-$MODELO/best.pt}
BORRAR=${BORRAR:-no}
MIN_LIBRE_GB=${MIN_LIBRE_GB:-60}
LOG=logs/barrer_territorio.log

cd "$HOME/castros" || exit 1
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

[ -f "$CKPT" ] || { say "no existe el checkpoint $CKPT"; exit 1; }
[ $# -ge 1 ] || { say "uso: $0 <fichero de bloques: nombre W S E N por linea>"; exit 2; }

say "### barrido por tandas | modelo $MODELO | borrar=$BORRAR ###"

while read -r NOM W S E N; do
  case "$NOM" in ""|\#*) continue;; esac
  OUT="data/sweep_territorio_${NOM}_${MODELO}.tsv"
  DIR="data/external/lidar-tanda-${NOM}"

  # ¿ya barrido? Se mide por filas, no por existencia: un fichero a medias
  # engaña, y eso ya costo dar un Pontevedra al `79%` por completo.
  if [ -s "$OUT" ] && [ "$(wc -l < "$OUT")" -gt 500 ]; then
    say "SALTO $NOM: ya tiene $(wc -l < "$OUT") filas"
    continue
  fi

  LIBRE=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc '0-9')
  if [ "${LIBRE:-0}" -lt "$MIN_LIBRE_GB" ]; then
    say "*** solo ${LIBRE}GB libres (minimo $MIN_LIBRE_GB): parando aqui ***"
    exit 3
  fi

  say "=== $NOM: descargando teselas ($LIBRE GB libres) ==="
  mkdir -p "$DIR"
  .venv-gpu/bin/python scripts/download_trasancos_lidar.py \
    --bbox "$W" "$S" "$E" "$N" --laz-dir "$DIR" --out-dir "$DIR" \
    --workers 4 --min-free-gb "$MIN_LIBRE_GB" 2>&1 \
    | grep -avE "^ *%|Dload|Current|^[0-9 ]*$|--:--:--|[0-9]+ +[0-9.]+[Mk]" >> "$LOG"
  NT=$(ls "$DIR"/*.laz 2>/dev/null | wc -l)
  say "$NOM: $NT teselas en disco"
  [ "$NT" -eq 0 ] && { say "$NOM sin teselas: se salta"; continue; }

  say "=== $NOM: barriendo ==="
  CASTROS_VRAM_FRAC=0.45 scripts/lanzar.sh "tanda-$NOM" 6000M \
    .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir "$DIR" --checkpoint "$CKPT" --out "$OUT" \
    --bbox "$W" "$S" "$E" "$N" \
    --workers 1 --batch 12 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
  say "$NOM barrido rc=$?  filas=$(wc -l < "$OUT" 2>/dev/null || echo 0)"

  if [ "$BORRAR" = "si" ]; then
    rm -rf "$DIR"
    say "$NOM: teselas borradas, disco libre $(df -BG --output=avail "$HOME" | tail -1 | tr -dc '0-9')GB"
  fi
done < "$1"

say "### barrido por tandas terminado ###"
