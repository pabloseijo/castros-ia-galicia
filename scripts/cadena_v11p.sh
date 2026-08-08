#!/bin/sh
# Encadena: corpus v11p (ya corriendo) -> entrenamiento de v11p.
#
# **v11p no es una version mas de la serie refutada.** Es un PUNTO DE DOSIS: el
# corpus de v7 tiene `773` positivos de entrenamiento, este tendra ~`2.100`, y el
# v11 definitivo tendra ~`3.800` cuando acabe la descarga. Con tres puntos se ve
# **cuanto** ayuda mas dato y si satura; con uno solo se sabria unicamente si
# «mejora» o «no mejora».
#
# ## Como espera, y por que asi
#
# Espera **por unidad de systemd**, no con `while pgrep -f patron`. El 2026-08-08
# ese patron fallo cuatro veces en una tarde: `pgrep -f` encuentra la linea de
# comandos del propio guion que pregunta, asi que un vigilante mio llego a
# bloquear una cadena `35` minutos y varias ordenes mias se mataron a si mismas.
# `systemctl --user is-active` pregunta por unidad y no puede autoencontrarse.
#
# Y espera a la GPU **justo antes del paso que la usa**, no al principio: v10
# fallo por eso —espero al arrancar, minio `20` minutos, y al ir a entrenar la
# GPU ya estaba cogida—.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v11p.log
say() { echo "[$(date +%F' '%H:%M)] $*" >> "$LOG"; }

esperar_unidad() {
  say "esperando a que termine $1"
  while systemctl --user is-active "$1" >/dev/null 2>&1; do sleep 120; done
  say "$1 ha terminado"
}

say "### cadena v11p: punto de dosis ###"
esperar_unidad castros-corpus-v11p.scope

IDX=data/galicia-vignettes-v11p/index.tsv
if [ ! -s "$IDX" ]; then
  say "*** el corpus v11p no tiene index.tsv: abortando ***"
  exit 1
fi
N=$(( $(wc -l < "$IDX") - 1 ))
POS=$(awk -F'\t' 'NR>1 && $3 ~ /^castro/ {n++} END{print n+0}' "$IDX")
TRAIN=$(awk -F'\t' 'NR>1 && $3 ~ /^castro/ && $8=="train" {n++} END{print n+0}' "$IDX")
say "corpus v11p: $N vinnetas | $POS castros | $TRAIN en entrenamiento"

# **Control preregistrado**: si los positivos de entrenamiento no superan de
# largo los `773` de v7, esto no es un punto de dosis y no vale la pena entrenar.
if [ "$TRAIN" -lt 1200 ]; then
  say "*** solo $TRAIN positivos en train (v7 tiene 773): no hay dosis, abortando ***"
  exit 1
fi

# ## Los controles del preregistro, ANTES de entrenar
#
# El `PREREGISTRO-v11` los exige antes de mirar ningun `F1`. Se ejecutan aqui
# para que no dependan de que yo me acuerde.
#
# **Que aborta y que no.** Abortan las dos cosas que harian la comparacion
# invalida: que el conjunto de validacion no sea el mismo que el de v7 —entonces
# `selection_best` deja de ser comparable— y que el precinto de Portugal este
# comprometido. **No aborta** la mezcla de bloques con `test_o_val`: es un
# defecto **preexistente e identico en v7**, medido el 2026-08-08 en `1` de los
# `7` castros de O Val (O Castrillon, a `461 m`), y como afecta igual a los dos
# lados de la comparacion, no la sesga. Se declara y se sigue.
say "=== controles del preregistro ==="
scripts/../.venv-gpu/bin/python scripts/controles_v11.py \
  --nuevo data/galicia-vignettes-v11p \
  --referencia data/galicia-vignettes-v7 >> "$LOG" 2>&1
say "controles rc=$? (el codigo 1 puede ser solo la mezcla de bloques, ver arriba)"

if grep -q "PRECINTO COMPROMETIDO\|precinto: NO se puede comprobar\|FALLA:.*sellados" "$LOG"; then
  say "*** PRECINTO COMPROMETIDO: abortando, esto no se entrena ***"
  exit 1
fi
if grep -q "selection_best NO es comparable" "$LOG"; then
  say "*** la validacion no coincide con v7: la dosis no seria comparable, abortando ***"
  exit 1
fi
say "controles: nada que impida entrenar (la mezcla de bloques queda declarada)"

# la GPU, justo antes de usarla
say "esperando GPU libre"
while systemctl --user is-active castros-barrido-lugo-v10.scope >/dev/null 2>&1 \
   || systemctl --user is-active castros-vision7b.scope >/dev/null 2>&1; do
  sleep 120
done
say "GPU libre"

say "=== entrenando v11p ==="
CASTROS_VRAM_FRAC=0.75 scripts/lanzar.sh entreno-v11p 4G \
  .venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v11p --out-dir data/cls-v11p \
  --head cls --encoder resnet34 --epochs 16 --batch 16 --workers 3 \
  --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
say "entrenamiento v11p rc=$?"

if [ -f data/cls-v11p/metrics.json ]; then
  S=$(.venv-gpu/bin/python -c "import json;print(json.load(open('data/cls-v11p/metrics.json')).get('selection_best'))" 2>/dev/null)
  say "selection_best de v11p: $S   (v7: 0.4605 | corte de cribado: 0.40)"
fi
say "### cadena v11p terminada ###"
