#!/bin/bash
# v9 = v8 mas la ortofoto en fusion temprana. Siete canales.
#
#   1 MDT normalizado   2 relieve local   3 pendiente   4 apertura
#   5 R                 6 G               7 B
#
# **Por que, y por que no es la criba refutada.** El 2026-08-07 se probo un
# clasificador de ortofoto como CRIBA POSTERIOR sobre candidatos ya detectados y
# salio anticorrelado: la precision de despliegue cayo de 0.200 a 0.062, porque
# aprendio «rural contra urbano» y en la ria de Vigo los castros estan rodeados
# de urbanizacion. Eso sigue refutado, COMO CRIBA.
#
# Peker (2026, 10.1017/aap.2025.10142) hace lo contrario sobre terrazas
# agricolas: mete lo espectral como CANAL DE ENTRADA y compara cuatro
# arquitecturas —temprana, intermedia, tardia y solo RGB—. Gana la temprana, con
# IoU 0.754, y su modelo saca mas precision que la digitalizacion experta (87,4%
# contra 79,3%). Filtrar al final no es lo mismo que dejar que la red aprenda a
# combinar textura y relieve desde el principio.
#
# Ataca el cuello mas caro medido: la precision cae de 0.826 en Lugo a 0.391 en
# Pontevedra, donde el confusor es obra moderna en paisaje periurbano. Justo lo
# que una imagen ve y un modelo digital del terreno no.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/cadena_v9.log
mkdir -p logs
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

ORTO_CORPUS=data/ortofotos-corpus
ORTO_REJILLA=data/ortofotos-rejilla

say "### v9: ortofoto en fusion temprana ###"

say "=== esperando a que v8 termine (corpus, entrenamiento y barridos) ==="
while pgrep -f "recortar[_]corpus_con_apertura.py|train_unet[_]multiclass.py|sweep_grid[_]lidar.py" > /dev/null 2>&1; do
  sleep 120
done
sleep 20

# El corpus de v9 es el MISMO que el de v8: los cuatro canales topograficos no
# cambian y el color se concatena al vuelo. No se duplica nada.
N=$(( $(wc -l < data/galicia-vignettes-v8/index.tsv 2>/dev/null || echo 1) - 1 ))
say "corpus (compartido con v8): $N vinnetas"
[ "$N" -lt 14000 ] && { say "*** corpus corto ($N): abortando ***"; exit 1; }

NO=$(ls "$ORTO_CORPUS" 2>/dev/null | wc -l)
say "ortofotos de corpus: $NO"
if [ "$NO" -lt 14000 ]; then
  say "*** faltan ortofotos de corpus ($NO de ~15311) ***"
  say "    las baja la Raspberry y las trae el orquestador con rsync"
  exit 1
fi

say "=== entrenando v9 (7 canales) ==="
.venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v8 --rgb-dir "$ORTO_CORPUS" \
  --out-dir data/cls-v9 \
  --head cls --encoder resnet34 --epochs 16 --batch 12 --workers 3 \
  --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
RC=$?; say "entrenamiento rc=$RC"
[ "$RC" -ne 0 ] && { say "*** ENTRENAMIENTO v9 FALLO ***"; exit "$RC"; }

# El barrido tambien necesita color, y se niega a correr sin el: ver la guardia
# de sweep_grid_lidar.py. Sin ella rellenaria las 8.658 celdas con gris neutro y
# puntuaria tres canales inexistentes, sin fallar y dando cifras peores.
NR=$(ls "$ORTO_REJILLA" 2>/dev/null | wc -l)
say "ortofotos de rejilla: $NR (hacen falta ~32444)"
if [ "$NR" -lt 30000 ]; then
  say "*** faltan ortofotos de rejilla: se entreno v9 pero no se puede barrer ***"
  exit 1
fi

for B in lugo coruna ourense pontevedra; do
  case $B in
    lugo)       BB="-7.375 42.625 -7.125 42.875";;
    pontevedra) BB="-8.875 42.125 -8.625 42.375";;
    coruna)     BB="-8.50 43.00 -8.25 43.25";;
    ourense)    BB="-8.25 42.25 -8.00 42.50";;
  esac
  .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
    --laz-dir data/external/lidar-val-$B --checkpoint data/cls-v9/best.pt \
    --out data/sweep_val_${B}_v9.tsv --bbox $BB \
    --ortofoto-dir "$ORTO_REJILLA" --ortofoto-prefijo "${B}_" \
    --workers 2 --batch 12 --chunk 200 >> "$LOG" 2>&1
  say "barrido $B rc=$?"
  say "=== EVALUACION $B v9, metro fusionado ==="
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_val_${B}_v9.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv \
    --umbrales 0.5 0.7 0.8 0.9 >> "$LOG" 2>&1
  .venv-gpu/bin/python scripts/extraer_candidatos.py \
    --pred data/sweep_val_${B}_v9.tsv --truth data/${B}_fus_truth_limpia.tsv \
    --mascara data/${B}_fus_mascara_train.tsv --umbral 0.7 \
    --out data/candidatos_${B}_v9.tsv >> "$LOG" 2>&1
done

say "=== referencia v7, metro fusionado, umbral 0.70 ==="
say "  Lugo 0.826/0.697 | Coruna 0.769/0.396 | Ourense 0.543/0.535 | Pontevedra 0.391/0.419"
say "### v9 completa ###"
