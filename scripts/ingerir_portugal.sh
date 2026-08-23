#!/bin/sh
# Recoge lo que Pablo deje del portal de la DGT, lo barre y borra el original.
#
# Instrucciones de descarga: DESCARGA-PORTUGAL.md
# Plan de peticiones:        data/plan-descarga-portugal.tsv
#
# ## Por qué baja-barre-borra y no baja-todo-y-luego-barre
#
# Las 76 peticiones son ~5,3 TB si se piden como nube de puntos y ~240 GB como
# ráster de 50 cm. En `oval-server` hay 166 GB libres. Recorriendo el conjunto
# en vez de teniéndolo, el pico de disco es **una petición**, no el total.
#
# ## Lo que NO hace, y es deliberado
#
# **No evalúa contra la verdad precintada.** `detection_eval.py` se niega sin
# `--romper-precinto "motivo"`, y esa orden la da una persona, no un guion. Esto
# deja los barridos hechos y para ahí.
set -u
cd "$(dirname "$0")/.." || exit 1
ENTRADA=data/entrada-portugal
LOG=logs/ingerir_portugal.log
KEEP_INPUT=${PORTUGAL_KEEP_INPUT:-0}
say() { echo "[$(date +%F\ %H:%M)] $*" >> "$LOG"; }

[ -d "$ENTRADA" ] || { say "no existe $ENTRADA — nada que ingerir"; exit 0; }

for D in "$ENTRADA"/*/; do
  [ -d "$D" ] || continue
  N=$(basename "$D")
  OUT="data/sweep_test_portugal_${N}.tsv"
  OUTFULL="data/sweep_test_portugal_${N}_fusion_rrf_full.tsv"

  if [ -f "$OUT" ] && [ "$(wc -l < "$OUT")" -gt 1 ]; then
    say "peticion $N ya fusionada ($(wc -l < "$OUT") filas) — se salta"
    continue
  fi

  N_LAZ=$(find "$D" -iname "*.laz" | wc -l)
  N_TIF=$(find "$D" -iname "*.tif" -o -iname "*.tiff" | wc -l)
  say "=== peticion $N: $N_LAZ ficheros LAZ, $N_TIF GeoTIFF ==="
  [ "$N_LAZ" -eq 0 ] && [ "$N_TIF" -eq 0 ] && { say "  vacia — se salta"; continue; }

  # El bbox se saca del propio plan, no se teclea. La regla del proyecto.
  BB=$(.venv-gpu/bin/python - "$N" <<'PY'
import csv, sys
n = sys.argv[1]
for r in csv.DictReader(open("data/plan-descarga-portugal.tsv"), delimiter="\t"):
    if r["orden"] == n:
        print("%s %s %s %s" % (r["lon_min"], r["lat_min"], r["lon_max"], r["lat_max"]))
        break
PY
)
  case "$BB" in
    [-0-9]*\ [-0-9]*\ [-0-9]*\ [-0-9]*) : ;;
    *) say "  *** sin bbox para la peticion $N en el plan — se salta ***"; continue ;;
  esac
  say "  bbox=$BB"

  if [ "$N_LAZ" -gt 0 ]; then
    # **Se barre la configuración congelada, no un checkpoint único.** Desde el
    # 2026-08-11 `data/CHECKPOINT-CONGELADO` contiene la receta
    # `fusion-rango:v7,v7last,v8,v12`, así que pasar su contenido a
    # `--checkpoint` sería un falso barrido. Cada modelo puntúa la misma rejilla
    # y después se fusiona por RRF.
    MODELOS="v7:data/cls-v7/best.pt v7last:data/cls-v7/last.pt v8:data/cls-v8/best.pt v12:data/cls-v12/best.pt"
    PREDS=""
    NAMES=""
    for MC in $MODELOS; do
      M=${MC%%:*}
      CK=${MC#*:}
      PRED="data/sweep_test_portugal_${N}_${M}.tsv"
      PREDS="$PREDS $PRED"
      NAMES="$NAMES $M"
      if [ -f "$PRED" ] && [ "$(wc -l < "$PRED")" -gt 1 ]; then
        say "  --- $M ya barrido ($(wc -l < "$PRED") filas) ---"
        continue
      fi
      [ -f "$CK" ] || { say "  *** falta checkpoint $CK para $M ***"; exit 1; }
      say "  --- barrido $M desde nube, diezmada a densidad PNOA ---"
      CASTROS_VRAM_FRAC=0.80 scripts/lanzar.sh "pt-$N-$M" 6500M \
        .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
        --laz-dir "$D" --checkpoint "$CK" \
        --out "$PRED" --bbox $BB --grid-crs EPSG:3763 --densidad-suelo 2.0 \
        --workers 1 --batch 12 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
      say "  rc=$? $M filas=$(wc -l < "$PRED" 2>/dev/null || echo 0)"
    done
    say "  --- fusion RRF top 100 ---"
    .venv-gpu/bin/python scripts/fusionar_barridos_rrf.py \
      --pred $PREDS --names $NAMES --out-full "$OUTFULL" --out-top "$OUT" \
      --top-k 100 --rrf-k 60 >> "$LOG" 2>&1
    say "  fusion filas=$(wc -l < "$OUT" 2>/dev/null || echo 0) full=$(wc -l < "$OUTFULL" 2>/dev/null || echo 0)"
  else
    say "  *** solo hay GeoTIFF: la via del raster NO esta validada como"
    say "      equivalente. Ver DESCARGA-PORTUGAL.md seccion 2. No se barre. ***"
    continue
  fi

  if [ "$(wc -l < "$OUT" 2>/dev/null || echo 0)" -gt 1 ] && [ "${PORTUGAL_AI_REVIEW:-1}" != "0" ]; then
    REV="data/revision-portugal/orden-$N"
    MORFO="$REV/triage_morfologico.tsv"
    mkdir -p "$REV"
    if [ ! -f "$MORFO" ] || [ "$(wc -l < "$MORFO" 2>/dev/null || echo 0)" -le 1 ]; then
      say "  --- bot morfologico Portugal top 100 ---"
      .venv-gpu/bin/python scripts/triage_morfologico.py \
        --puntos "$OUT" --laz-dir "$D" --crs EPSG:3763 --out "$MORFO" \
        --workers "${PORTUGAL_MORFO_WORKERS:-1}" >> "$LOG" 2>&1
      MF=$(wc -l < "$MORFO" 2>/dev/null || echo 0)
      say "  morfo filas=$MF"
      # El triaje murio por OOM en 5 de las 13 primeras ordenes y el guion
      # seguia como si nada. Que al menos quede gritado en el log.
      [ "$MF" -le 1 ] && say "  *** AVISO: el triaje morfologico NO produjo nada (probable OOM). La orden sigue siendo valida: el entregable es la fusion. ***"
    else
      say "  --- bot morfologico ya existe ($(wc -l < "$MORFO") filas) ---"
    fi

    if command -v curl >/dev/null 2>&1 && curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      say "  --- revision visual IA local con Ollama (${PORTUGAL_AI_MODEL:-qwen2.5vl:7b}) ---"
      .venv-gpu/bin/python scripts/portugal_visual_ai_review.py \
        --candidatos "$OUT" --dem-dir "$D" --morpho "$MORFO" \
        --out-dir "$REV" --top-n "${PORTUGAL_AI_TOP_N:-20}" \
        --model "${PORTUGAL_AI_MODEL:-qwen2.5vl:7b}" >> "$LOG" 2>&1
      say "  revision IA: $REV"
    else
      say "  --- Ollama no disponible; se salta revision IA local ---"
    fi
  fi

  if [ "$(wc -l < "$OUT" 2>/dev/null || echo 0)" -gt 100 ] && [ "$KEEP_INPUT" = "1" ]; then
    say "  --- barrido valido; PORTUGAL_KEEP_INPUT=1, se conserva el original ---"
  elif [ "$(wc -l < "$OUT" 2>/dev/null || echo 0)" -gt 100 ]; then
    say "  --- borrando el original de la peticion $N ---"
    rm -rf "$D"
    say "  borrado. Disco libre: $(df -h / | awk 'NR==2{print $4}')"
  else
    say "  *** el barrido salio corto: NO se borra el original ***"
  fi
done

say "=== resumen ==="
for F in data/sweep_test_portugal_*.tsv; do
  [ -f "$F" ] && say "  $(basename "$F"): $(wc -l < "$F") filas"
done
say "### ingesta de Portugal terminada ###"
say "El precinto NO se ha tocado: evaluar exige --romper-precinto y lo hace una persona."
