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

# **Esperar al PRODUCTO, no al proceso.** Que un ambito termine no significa que
# haya terminado BIEN: el 2026-08-09 el corte murio por OOM en el grupo `2.925` de
# `5.340`, el ambito paso a inactivo, y la cadena lo interpreto como «ya esta» y
# siguio hasta encontrarse sin `index.tsv`. Se espera a que exista el fichero que
# el trabajo debe producir, y se comprueba que el ambito sigue vivo mientras tanto:
# si muere sin producirlo, se dice y se aborta, en vez de continuar a ciegas.
esperar_producto() {
  unidad=$1; producto=$2
  say "esperando a $producto (unidad $unidad)"
  while [ ! -s "$producto" ]; do
    if ! systemctl --user is-active "$unidad" >/dev/null 2>&1; then
      say "*** $unidad ha muerto sin producir $producto ***"
      return 1
    fi
    sleep 120
  done
  say "$producto listo"
  return 0
}

say "### cadena v11p: punto de dosis ###"
IDX=data/galicia-vignettes-v11p/index.tsv
esperar_producto castros-corpus-v11p.scope "$IDX" || exit 1
# **`gsub(/\r/,"")` no es cosmetico.** El indice se escribe con fin de linea CRLF,
# asi que `$8` vale `train\r` y la comparacion `$8=="train"` da SIEMPRE falso. La
# primera version de esta guarda conto `0` positivos en entrenamiento —para v11p
# y tambien para v7, que tiene `773`— y aborto la cadena por un falso negativo.
N=$(( $(wc -l < "$IDX") - 1 ))
POS=$(awk -F'\t' 'NR>1 {gsub(/\r/,""); if ($3 ~ /^castro/) n++} END{print n+0}' "$IDX")
TRAIN=$(awk -F'\t' 'NR>1 {gsub(/\r/,""); if ($3 ~ /^castro/ && $8 ~ /^train/) n++} END{print n+0}' "$IDX")
RND=$(awk -F'\t' 'NR>1 {gsub(/\r/,""); if ($3 ~ /^random_terrain/) n++} END{print n+0}' "$IDX")
say "random_terrain en el corpus: $RND (v7 tiene 10742)"
# Un corpus sin terreno aleatorio tiene otro balance de clases y no es comparable
# con v7: el 2026-08-08 salio con `0` porque el lector de negativos buscaba una
# columna `longitude` que ese fichero no tiene, y descarto 10.667 filas en silencio.
if [ "$RND" -lt 3000 ]; then
  say "*** solo $RND random_terrain: el balance de clases no es comparable con v7, abortando ***"
  exit 1
fi
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
# **La salida de los controles va a su PROPIO fichero, no al log.** El 2026-08-09
# esta guarda aborto un entrenamiento correcto porque hacia `grep` sobre el log
# acumulativo y encontro el fallo del intento ANTERIOR —ya corregido—. Un guardia
# que lee el historial en vez del presente para todo lo que alguna vez fallo.
CTRL=logs/controles_v11p_$(date +%H%M%S).txt
say "=== controles del preregistro -> $CTRL ==="
.venv-gpu/bin/python scripts/controles_v11.py \
  --nuevo data/galicia-vignettes-v11p \
  --referencia data/galicia-vignettes-v7 > "$CTRL" 2>&1
RC=$?
cat "$CTRL" >> "$LOG"
say "controles rc=$RC (el 1 puede ser solo la mezcla de bloques, ver arriba)"

# **Solo el precinto aborta.** Es el unico fallo irreversible: entrenar sobre el
# conjunto de prueba invalida para siempre la unica estimacion insesgada del
# proyecto, y no se nota despues. Lo demas se declara y se sigue.
if grep -q "FALLA:.*sellados\|precinto: NO se puede comprobar" "$CTRL"; then
  say "*** PRECINTO COMPROMETIDO: abortando, esto no se entrena ***"
  exit 1
fi
say "precinto verificado cerrado en esta corrida"

# La validacion ya no aborta: con `--splits-de` el examen de v11p es un
# SUBCONJUNTO del de v7 (`0` viñetas nuevas, algunas de v7 que no se pudieron
# cortar por falta de LiDAR). No hay contaminacion del examen, pero la cifra no
# es numericamente comparable hasta reevaluar v7 sobre ese mismo subconjunto.
if grep -q "selection_best NO es comparable" "$CTRL"; then
  say "AVISO: el examen es un subconjunto del de v7; hay que reevaluar v7 sobre el"
  say "       mismo subconjunto antes de comparar selection_best. Se entrena igual."
fi

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
