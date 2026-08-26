#!/bin/sh
# v15: la agregación espacial, un mecanismo con dos tratamientos.
# Preregistro en `docs/preregistros/PREREGISTRO-v15-cabeza-mil.md`, escrito ANTES de esto.
#
# El control es v7 (media global, F1 0,512). Los dos brazos:
#   v15a = log-sum-exp  (--head mil)      implementado desde el principio,
#                                         nunca entrenado en 9 checkpoints
#   v15b = atención     (--head atencion) implementado el 2026-08-10 siguiendo
#                                         a Ilse et al., ICML 2018
#
# Mismo corpus, mismo split, misma pérdida, mismas épocas que v7. Solo cambia
# la cabeza, para que el resultado sea atribuible.
#
# **Espera a que la GPU se libere de la cadena de v9.** La condición mira el
# fichero de bloqueo del propio wrapper, NO un `pgrep` con un patrón que pueda
# encontrarse a sí mismo: eso dejó la cadena de v9 dos horas parada el
# 2026-08-10.
set -u
cd "$(dirname "$0")/.." || exit 1
LOG=logs/cadena_v15.log
say() { echo "[$(date +%F\ %H:%M)] $*" | tee -a "$LOG"; }

# **La condición es el DATO, no el log.** El log ya contiene un
# «### cadena v9 terminada ###» de la corrida que abortó a las 15:09 del
# 2026-08-10 con `bbox` vacío, así que esperar a esa cadena dispararía al
# instante. Se espera a que los tres barridos tengan sus filas.
completos() {
  for B in lugo ourense coruna; do
    N=$(wc -l < "data/sweep_val_${B}_v9.tsv" 2>/dev/null || echo 0)
    R=$(wc -l < "data/sweep_val_${B}_v7.tsv" 2>/dev/null || echo 1)
    [ "$N" -ge $((R * 9 / 10)) ] || return 1
  done
  return 0
}

say "v15 no depende de v9: solo compite por la GPU, y eso lo resuelve el cerrojo"

# **Cola, no desalojo.** Si la GPU la tiene otro trabajo -el 2026-08-10 era un
# entrenamiento de voz de Pablo con la tarjeta en Exclusive_Process- se espera.
# **Cerrojo, no cadena de marcadores.** Antes cada cadena esperaba a que la
# anterior escribiera "terminada" en su log. Eso encadenaba tres esperas SIN
# PLAZO: si v9 no llegaba a completarse, v15 esperaba para siempre y arrastraba
# a last_pt y a v17. Un punto único de fallo para toda la cola.
#
# Y era innecesario: v15 entrena sobre el corpus de v7 y **no depende de v9
# para nada**; esperaba solo para no competir por la GPU. Eso es exactamente
# para lo que sirve un cerrojo.
#
# `flock` serializa de verdad —el que no lo tiene, espera— y con `-w` se puede
# poner plazo, así que ninguna cadena puede quedarse colgada de otra.
GPU_LOCK=data/gpu.lock
: > "$GPU_LOCK" 2>/dev/null || true
con_gpu() {   # con_gpu <segundos de plazo> <orden...>
  PLAZO=$1; shift
  flock -w "$PLAZO" 9 || { say "no consegui el cerrojo de GPU en ${PLAZO}s: sigo igual"; }
  "$@"
} 9>>"$GPU_LOCK"

esperar_gpu() {
  if ! scripts/gpu_libre.sh; then
    say "GPU ocupada por otro trabajo: esperando"
    until scripts/gpu_libre.sh; do sleep 300; done
    say "GPU libre"
  fi
}

esperar_gpu

for BRAZO in a b; do
  case "$BRAZO" in
    a) CABEZA=mil ;;
    b) CABEZA=atencion ;;
  esac
  OUT="data/cls-v15$BRAZO"
  esperar_gpu
  say "=== entrenando v15$BRAZO (cabeza $CABEZA) ==="
  con_gpu 43200 env CASTROS_VRAM_FRAC=0.85 .venv-gpu/bin/python scripts/train_unet_multiclass.py \
    --vig-dir data/galicia-vignettes-v7 --out-dir "$OUT" \
    --head "$CABEZA" --encoder resnet34 --epochs 16 --batch 16 --workers 2 \
    --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
  RC=$?
  say "v15$BRAZO rc=$RC"
  [ -f "$OUT/best.pt" ] || { say "*** sin checkpoint para v15$BRAZO ***"; continue; }

  # La medida que este proyecto no tiene en sus quince checkpoints, y que es
  # la prueba del MECANISMO, separada de la prueba del resultado.
  say "--- error de entrenamiento de v15$BRAZO ---"
  .venv-gpu/bin/python scripts/error_de_entrenamiento.py \
    --modelo "v15$BRAZO" --vig data/galicia-vignettes-v7 >> "$LOG" 2>&1
done

say "### cadena v15 terminada ###"
