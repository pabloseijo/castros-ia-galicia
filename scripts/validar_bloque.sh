#!/bin/bash
# Valida un bloque fuera del piloto: descarga -> barre -> comprueba cobertura ->
# evalua solo contra lo no visto. Generico, porque quedan siete bloques.
#
# El orden importa y esta aprendido a golpes:
#  - la cobertura se comprueba ANTES de dar cifras. El primer barrido de Lugo se
#    quedo al 59% y su F1 medía la cobertura, no el modelo.
#  - la mascara de contaminacion se aplica siempre. En Lugo, 33 de 93 castros
#    estaban en train o val; sin enmascarar, F1 0.644 en vez de 0.590.
#  - 2 obreros. El OOM se llevo el barrido cuatro veces con 3 o mas.
#
# Uso: ./validar_bloque.sh <nombre> <W> <S> <E> <N>
set -u
[ $# -lt 5 ] && { echo "uso: $0 <nombre> <W> <S> <E> <N>"; exit 2; }
NOMBRE=$1; W=$2; S=$3; E=$4; N=$5
cd "$HOME/castros" || exit 1
LOG="logs/validar_${NOMBRE}.log"
mkdir -p logs data
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

LIBRE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9')
say "=== bloque $NOMBRE ($W $S $E $N), ${LIBRE} GB libres ==="
[ "$LIBRE" -lt 120 ] && { say "ABORTA: hacen falta 120 GB"; exit 1; }

say "--- verdad de campo y mascara de contaminacion ---"
.venv-gpu/bin/python scripts/preparar_bloque_validacion.py \
  --nombre "$NOMBRE" --bbox $W $S $E $N >> "$LOG" 2>&1

say "--- descargando LiDAR (3 conexiones, cortesia con el CNIG) ---"
.venv-gpu/bin/python scripts/download_trasancos_lidar.py --bbox $W $S $E $N \
  --out-dir "data/lidar-val-$NOMBRE" --laz-dir "data/external/lidar-val-$NOMBRE" \
  --workers 3 --min-free-gb 60 >> "$LOG" 2>&1
T=$(ls data/external/lidar-val-$NOMBRE/*.laz 2>/dev/null | wc -l)
say "descargadas $T teselas ($(du -sh data/external/lidar-val-$NOMBRE 2>/dev/null | cut -f1))"
[ "$T" -lt 20 ] && { say "ABORTA: solo $T teselas"; exit 1; }

say "--- barriendo con v3 sin reentrenar ---"
.venv-gpu/bin/python scripts/sweep_grid_lidar.py \
  --laz-dir "data/external/lidar-val-$NOMBRE" --checkpoint data/cls-v3/best.pt \
  --out "data/sweep_val_$NOMBRE.tsv" --bbox $W $S $E $N \
  --workers 2 --batch 16 >> "$LOG" 2>&1
say "barrido: $(wc -l < data/sweep_val_$NOMBRE.tsv 2>/dev/null) celdas"

say "--- COBERTURA (antes de mirar ninguna cifra) ---"
.venv-gpu/bin/python - "$NOMBRE" >> "$LOG" 2>&1 <<'PY'
import csv, sys
import numpy as np
n = sys.argv[1]
sw = list(csv.DictReader(open("data/sweep_val_%s.tsv" % n, encoding="utf-8"), delimiter="\t"))
tr = list(csv.DictReader(open("data/%s_truth_limpia.tsv" % n, encoding="utf-8"), delimiter="\t"))
lat0 = float(np.mean([float(t["lat"]) for t in tr])); k = 111320.0
kx = k * np.cos(np.radians(lat0))
sx = np.array([float(r["lon"]) for r in sw]) * kx
sy = np.array([float(r["lat"]) for r in sw]) * k
d = np.array([float(np.hypot(sx - float(t["lon"]) * kx, sy - float(t["lat"]) * k).min()) for t in tr])
print("COBERTURA: %d de %d castros con celda a <256 m (%.0f%%)" % ((d <= 256).sum(), len(d), 100 * (d <= 256).mean()))
print("  mediana %.0f m | peor %.0f m | sin cobertura (>512 m): %d" % (np.median(d), d.max(), (d > 512).sum()))
if (d <= 256).mean() < 0.95:
    print("AVISO: cobertura insuficiente. La cifra de abajo mide el barrido, no el modelo.")
PY

say "--- evaluacion contra lo NO visto ---"
.venv-gpu/bin/python scripts/detection_eval.py \
  --pred "data/sweep_val_$NOMBRE.tsv" --truth "data/${NOMBRE}_truth_limpia.tsv" \
  --mascara "data/${NOMBRE}_mascara_train.tsv" \
  --umbrales 0.1 0.2 0.3 0.4 0.5 0.6 0.7 >> "$LOG" 2>&1
say "referencias: Trasancos F1 0.415 (costa/industria) | Lugo F1 0.590 (interior)"

say "--- cache de DEM del bloque ---"
.venv-gpu/bin/python scripts/laz_a_dem.py --laz-dir "data/external/lidar-val-$NOMBRE" \
  --out "data/dem-cache-$NOMBRE" --workers 8 >> "$LOG" 2>&1
say "=== bloque $NOMBRE completo ==="
