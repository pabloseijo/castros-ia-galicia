#!/bin/bash
# Descarga el LiDAR de los bloques de validacion que faltan para cerrar Galicia.
#
# El precinto de Portugal no se puede romper hasta tener cerrada la
# configuracion sobre TODOS los bloques gallegos, y hoy solo hay tres:
# Trasancos, Lugo y Pontevedra. Faltan la fachada atlantica norte (A Coruna) y
# el interior sur (Ourense).
#
# Los recuadros NO se eligieron a ojo. Se cruzo el catalogo (3.071 castros)
# contra todo lo que el modelo vio en train/val, contando cuantos quedan
# limpios por celda de 0,25 grados:
#
#   A Coruna  -8.50 43.00 -8.25 43.25   70 castros nunca vistos
#   Ourense   -8.25 42.25 -8.00 42.50   34 castros nunca vistos
#
# Ourense sale flojo a proposito de la comparacion: tiene 478 castros
# catalogados en toda la provincia, muy por debajo de la densidad del norte.
# Puede ser densidad real menor o un catalogo peor; si es lo segundo, es donde
# mas castros ineditos habria y donde la "precision" mas engana.
#
# EN SECUENCIA, no en paralelo: el descargador ya abre 3 conexiones al CNIG,
# que es un servicio publico gratuito. Seis a la vez es abusar.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/descarga_bloques.log
mkdir -p logs
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

descargar() {
  local NOMBRE="$1"; shift
  local BBOX="$*"
  say "=== descargando $NOMBRE ($BBOX) ==="
  .venv-gpu/bin/python scripts/download_trasancos_lidar.py \
    --out-dir "data/lidar-val-$NOMBRE" \
    --laz-dir "data/external/lidar-val-$NOMBRE" \
    --bbox $BBOX >> "$LOG" 2>&1
  local RC=$?
  local N=$(ls "data/external/lidar-val-$NOMBRE"/*.laz 2>/dev/null | wc -l)
  local GB=$(du -sh "data/external/lidar-val-$NOMBRE" 2>/dev/null | cut -f1)
  say "$NOMBRE rc=$RC | teselas=$N | tamanno=$GB"
  if [ "$RC" -ne 0 ]; then
    say "*** DESCARGA $NOMBRE FALLO (rc=$RC) ***"
  fi
  say "disco libre: $(df -h "$HOME/castros" | tail -1 | awk '{print $4}')"
}

say "### inicio de descargas ###"
say "disco libre al empezar: $(df -h "$HOME/castros" | tail -1 | awk '{print $4}')"

descargar coruna  -8.50 43.00 -8.25 43.25
descargar ourense -8.25 42.25 -8.00 42.50

say "### descargas completas ###"
