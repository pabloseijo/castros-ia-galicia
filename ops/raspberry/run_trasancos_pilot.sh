#!/usr/bin/env bash
# Ejecuta el piloto de Trasancos entero en la Raspberry, sin supervision.
#
# Pensado para lanzarse una sola vez cuando la Pi vuelve de un reinicio fisico.
# Cada etapa es reanudable y comprueba sus condiciones antes de empezar, asi
# que si el disco vuelve a colgarse basta con relanzar este mismo script: no
# repite descargas ni recortes ya hechos.
#
#   ssh admin@raspberri 'setsid nohup /srv/data/castros-ia-galicia-current/ops/raspberry/run_trasancos_pilot.sh > /srv/data/pilot.log 2>&1 < /dev/null & disown'
#
# NO usa `set -e`: si una etapa falla queremos que las siguientes decidan por
# si mismas si pueden seguir, y sobre todo que el resumen final se imprima.
set -uo pipefail

WORKSPACE=/srv/data/castros-ia-galicia-current
MOUNT=/srv/data
PY=${PY:-python3}
MIN_FREE_GB=${MIN_FREE_GB:-60}
LOG_DIR="$WORKSPACE/logs-pilot"
mkdir -p "$LOG_DIR"

say() { echo; echo "=== $* ==="; }
fail() { echo "ABORTADO: $*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. guardas
say "0. Comprobaciones previas"

mountpoint -q "$MOUNT" || fail "$MOUNT no esta montado"

# La comprobacion que de verdad importa: un disco puede figurar montado y
# estar colgado, y `mountpoint` no lo detecta. Solo una escritura real con
# timeout lo distingue.
#
# Se escribe dentro del workspace, no en la raiz del montaje: /srv/data es
# root:root, asi que un touch ahi da "Permission denied" y no dice nada sobre
# la salud del disco. Probarlo en la raiz hacia fallar este guarda siempre.
PROBE="$WORKSPACE/.pilot-precheck"
if ! timeout 10 touch "$PROBE" 2>/dev/null; then
  fail "$WORKSPACE no escribible: disco colgado, o permisos rotos"
fi
rm -f "$PROBE"
echo "  escritura real en $WORKSPACE: OK"

FREE_GB=$(df -BG --output=avail "$MOUNT" | tail -1 | tr -dc '0-9')
echo "  espacio libre: ${FREE_GB} GB"
[ "$FREE_GB" -ge "$MIN_FREE_GB" ] || fail "menos de ${MIN_FREE_GB} GB libres"

THROTTLED=$(vcgencmd get_throttled 2>/dev/null || echo "n/a")
echo "  $THROTTLED  (0x0 = sin caida de tension)"

if systemctl is-active --quiet srv-data-watchdog.timer 2>/dev/null; then
  echo "  watchdog del disco: activo"
else
  echo "  AVISO: el watchdog NO esta activo. Ejecuta antes:"
  echo "         sudo $WORKSPACE/ops/raspberry/harden_external_disk.sh"
fi

HOME_ADMIN=$(getent passwd admin | cut -d: -f6)
case "$HOME_ADMIN" in
  "$MOUNT"*) echo "  AVISO GRAVE: el home de admin ($HOME_ADMIN) cuelga del disco externo;"
             echo "               si el disco se cuelga, SSH se cuelga con el." ;;
  *)         echo "  home de admin fuera del disco externo: OK" ;;
esac

cd "$WORKSPACE" || fail "no existe $WORKSPACE"

for mod in numpy laspy pyproj; do
  $PY -c "import $mod" 2>/dev/null || fail "falta el modulo $mod ($PY -m pip install $mod)"
done
echo "  dependencias python: OK"

# ------------------------------------------------------- 1. LiDAR de Trasancos
say "1. LiDAR de Trasancos (reanudable)"
BEFORE=$(ls data/external/lidar-trasancos-v1/*.laz 2>/dev/null | wc -l)
echo "  teselas ya en disco: $BEFORE"

$PY scripts/download_trasancos_lidar.py --workers 3 \
  >> "$LOG_DIR/1_lidar.log" 2>&1
RC=$?
AFTER=$(ls data/external/lidar-trasancos-v1/*.laz 2>/dev/null | wc -l)
echo "  teselas tras la etapa: $AFTER (rc=$RC)"
[ "$AFTER" -gt 0 ] || fail "no hay ninguna tesela LiDAR; nada que procesar"

# ------------------------------------------------------------- 2. Negativos
say "2. Negativos duros desde OSM (solo si faltan)"
if [ -s data/trasancos-hard-negatives-v1/trasancos_hard_negatives.tsv ]; then
  echo "  ya existen: $(( $(wc -l < data/trasancos-hard-negatives-v1/trasancos_hard_negatives.tsv) - 1 )) negativos"
else
  $PY scripts/build_trasancos_hard_negatives.py --per-class 350 \
    >> "$LOG_DIR/2_negativos.log" 2>&1
  echo "  generados (rc=$?)"
fi

# --------------------------------------------------------------- 3. Viñetas
say "3. Recorte de vinetas a 1 m"
$PY scripts/build_trasancos_vignettes.py --workers 3 \
  >> "$LOG_DIR/3_vinetas.log" 2>&1
RC=$?
echo "  rc=$RC"
tail -6 "$LOG_DIR/3_vinetas.log"

# ---------------------------------------------------------------- 4. Resumen
say "4. Resumen"
$PY - <<'PYEOF'
import csv, json, pathlib
from collections import Counter
d = pathlib.Path("data/trasancos-vignettes-v1")
idx = d / "index.tsv"
if not idx.exists():
    print("  sin index.tsv: la etapa 3 no llego a terminar")
    raise SystemExit
rows = list(csv.DictReader(open(idx, encoding="utf-8"), delimiter="\t"))
print(f"  vinetas: {len(rows)}")
for sp in ("train", "val", "test_o_val"):
    c = Counter(r["label"] for r in rows if r["split"] == sp)
    print(f"    {sp:12s} {c.get('1',0):4d} positivos, {c.get('0',0):5d} negativos")
oval = [r for r in rows if r["split"] == "test_o_val" and r["label"] == "1"]
print(f"  castros de O Val en el holdout: {len(oval)}/7")
meta = d / "meta.json"
if meta.exists():
    print("  meta:", json.loads(meta.read_text())["channels"])
PYEOF

say "HECHO"
echo "Para traer el resultado al Mac (el cache de vinetas es lo unico necesario"
echo "para entrenar, y pesa poco comparado con los LAZ):"
echo "  rsync -avz admin@raspberri:$WORKSPACE/data/trasancos-vignettes-v1/ ./data/trasancos-vignettes-v1/"
echo
echo "Logs por etapa en $LOG_DIR"
