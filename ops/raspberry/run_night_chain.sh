#!/usr/bin/env bash
# Cadena nocturna desatendida: encadena todo lo que no necesita GPU.
#
# Cada etapa es reanudable y comprueba sus condiciones antes de arrancar, asi
# que relanzar este script tras una caida continua donde estaba. No usa
# `set -e`: si una etapa falla queremos que las siguientes decidan por si
# mismas y que el resumen final se imprima igual.
#
# Orden deliberado. Las descargas van primero y en serie porque comparten un
# unico servicio publico gratuito (CNIG, Overpass) y dos descargadores a la vez
# son descortesia, no paralelismo. El computo pesado va despues, cuando la red
# ya esta libre y los nucleos son el recurso escaso.

set -uo pipefail

W=/srv/data/castros-ia-galicia-current
LOG=$W/logs-night
mkdir -p "$LOG"
cd "$W" || exit 1

# El paralelismo aqui es de proceso; sin esto la BLAS abre 5 hilos por worker.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

stamp() { date -u +%H:%M:%SZ; }
say()   { echo; echo "=== [$(stamp)] $* ==="; }

disk_ok() {
  mountpoint -q /srv/data || { echo "  /srv/data NO montado"; return 1; }
  timeout 10 touch "$W/.night-probe" 2>/dev/null || {
    echo "  disco montado pero NO escribible (colgado)"; return 1; }
  rm -f "$W/.night-probe"
  local free
  free=$(df -BG --output=avail /srv/data | tail -1 | tr -dc '0-9')
  echo "  disco OK, ${free} GB libres"
  [ "$free" -ge 40 ]
}

stage() {  # stage <nombre> <fichero-log> <comando...>
  local name=$1 log=$2; shift 2
  say "$name"
  if ! disk_ok; then echo "  ABORTADA: disco no disponible"; return 1; fi
  "$@" >> "$LOG/$log" 2>&1
  local rc=$?
  echo "  rc=$rc"
  tail -3 "$LOG/$log" 2>/dev/null | sed 's/^/  | /'
  return $rc
}

say "INICIO DE CADENA NOCTURNA"
disk_ok || exit 1
vcgencmd get_throttled 2>/dev/null | sed 's/^/  /'

# --- 1. Terminar lo que ya estuviera en marcha ---------------------------
say "Esperando a que terminen procesos previos"
for p in run_trasancos_pilot.sh download_positive_centred_lidar.py \
         build_trasancos_vignettes.py; do
  while pgrep -f "$p" > /dev/null; do sleep 60; done
done
echo "  ninguno activo"

# --- 2. LiDAR centrado en etiquetas (el que da poder estadistico) --------
stage "LiDAR centrado en positivos (1500 teselas)" 1_lidar_positivos.log \
  python3 scripts/download_positive_centred_lidar.py --budget 1500 --workers 3

# --- 3. Negativos con nombre a escala Galicia ---------------------------
# Sin esto la proporcion a escala gallega es 3:1 y no se parece al despliegue.
stage "Negativos con nombre, Galicia" 2_negativos_galicia.log \
  python3 scripts/build_trasancos_hard_negatives.py --scope galicia \
    --per-class 3000 --out-dir data/galicia-hard-negatives-v1

# --- 4. Vinetas a escala Galicia ----------------------------------------
stage "Vinetas, alcance Galicia" 3_vinetas_galicia.log \
  python3 scripts/build_trasancos_vignettes.py --scope galicia \
    --laz-dir data/external/lidar-positives-v1 \
    --out-dir data/galicia-vignettes-v1 --workers 3

# --- 5. Linea base entrenada sin GPU ------------------------------------
# sklearn esta instalado; un gradient boosting sobre estadisticos de las
# vinetas no sera un ConvNeXt, pero cierra el pipeline de punta a punta y da
# el primer numero medido con honest_eval. Sin esa referencia, cuando llegue
# la GPU no sabremos si la red aporta algo.
stage "Linea base CPU (gradient boosting)" 4_baseline_cpu.log \
  python3 scripts/train_cpu_baseline.py --vig-dir data/trasancos-vignettes-v1 \
    --out-dir data/cpu-baseline-v1

stage "Linea base CPU, alcance Galicia" 5_baseline_galicia.log \
  python3 scripts/train_cpu_baseline.py --vig-dir data/galicia-vignettes-v1 \
    --out-dir data/cpu-baseline-galicia-v1

# --- 6. Resumen ---------------------------------------------------------
say "RESUMEN"
python3 - <<'PYEOF'
import csv, json, pathlib
from collections import Counter
for name in ("trasancos-vignettes-v1", "galicia-vignettes-v1"):
    d = pathlib.Path("data") / name
    idx = d / "index.tsv"
    if not idx.exists():
        print(f"  {name}: sin index.tsv"); continue
    rows = list(csv.DictReader(open(idx, encoding="utf-8"), delimiter="\t"))
    c = Counter((r["split"], r["label"]) for r in rows)
    print(f"  {name}: {len(rows)} vinetas")
    for sp in ("train", "val", "test_o_val"):
        print(f"     {sp:12s} {c.get((sp,'1'),0):5d} positivos, {c.get((sp,'0'),0):6d} negativos")
for name in ("cpu-baseline-v1", "cpu-baseline-galicia-v1"):
    m = pathlib.Path("data") / name / "metrics.json"
    if m.exists():
        j = json.loads(m.read_text())
        print(f"  {name}: {json.dumps(j.get('summary', j))[:300]}")
PYEOF

say "CADENA NOCTURNA TERMINADA"
echo "Logs por etapa en $LOG"
