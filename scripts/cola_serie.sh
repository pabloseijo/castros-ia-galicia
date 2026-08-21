#!/bin/sh
# La cola entera, EN SERIE y en un solo proceso.
#
# Por qué existe: la madrugada del 2026-08-11 lancé cinco cadenas a la vez
# —v9, repesca, v15, last_pt, v17 y cachés de DEM— cada una con su espera de
# GPU y su cerrojo. El resultado fue un `global_oom` del kernel: **la máquina
# entera se quedó sin RAM**, no un tope de cgroup. Se llevó por delante dos
# barridos de Lugo a media ejecución. Y `oval-server` tiene 8 GB, que es
# exactamente lo que la regla del proyecto dice que no se apila.
#
# Un cerrojo `flock` no bastó porque serializaba los ENTRENAMIENTOS entre sí
# pero dejaba correr barridos en paralelo, y además invertía el orden: v15b, el
# experimento que decidía, quedó detrás de diez horas de barridos.
#
# La forma correcta es la más simple: **un proceso, una cosa detrás de otra**.
# Sin cerrojos, sin esperas cruzadas, sin cadenas que se esperen unas a otras.
# Si algo falla, se salta y sigue; nada se pierde porque los barridos reanudan.
set -u
cd "$(dirname "$0")/.." || exit 1
LOG=logs/cola_serie.log
say() { echo "[$(date +%F\ %H:%M)] $*" | tee -a "$LOG"; }

BB_lugo="-7.375 42.625 -7.125 42.875"
BB_coruna="-8.50 43.00 -8.25 43.25"
BB_ourense="-8.25 42.25 -8.00 42.50"
BB_pontevedra="-8.875 42.125 -8.625 42.375"
bbox() { eval "echo \$BB_$1"; }

completo() {   # $1=bloque  $2=sufijo
  N=$(wc -l < "data/sweep_val_${1}_${2}.tsv" 2>/dev/null || echo 0)
  R=$(wc -l < "data/sweep_val_${1}_v7.tsv" 2>/dev/null || echo 999999)
  [ "$N" -ge $((R * 9 / 10)) ]
}

barrer() {     # $1=bloque  $2=sufijo  $3=checkpoint  $4=extra
  B=$1; SUF=$2; CK=$3; EXTRA=${4:-}
  if completo "$B" "$SUF"; then
    say "$B/$SUF ya completo ($(wc -l < data/sweep_val_${B}_${SUF}.tsv) filas)"
    return 0
  fi
  I=1
  while [ "$I" -le 3 ]; do
    say "=== $B/$SUF intento $I ==="
    CASTROS_VRAM_FRAC=0.80 scripts/lanzar.sh "b-$B-$SUF-$I" 6500M \
      .venv-gpu/bin/python scripts/sweep_grid_lidar.py \
      --laz-dir "data/external/lidar-val-$B" --checkpoint "$CK" \
      --out "data/sweep_val_${B}_${SUF}.tsv" --bbox $(bbox "$B") $EXTRA \
      --workers 1 --batch 12 --chunk 100 --max-celdas-tarea 12 >> "$LOG" 2>&1
    say "$B/$SUF rc=$? filas=$(wc -l < data/sweep_val_${B}_${SUF}.tsv 2>/dev/null || echo 0)"
    completo "$B" "$SUF" && break
    I=$((I + 1))
  done
  say "--- evaluacion $B/$SUF ---"
  .venv-gpu/bin/python scripts/detection_eval.py \
    --pred "data/sweep_val_${B}_${SUF}.tsv" \
    --truth "data/${B}_fus_truth_limpia.tsv" \
    --mascara "data/${B}_fus_mascara_train.tsv" --umbral 0.70 >> "$LOG" 2>&1
}

say "### empieza la cola en serie ###"

# 1. Cerrar v9: es lo unico preregistrado con bloques a medias.
for B in lugo coruna; do
  barrer "$B" v9 data/cls-v9/best.pt \
    "--ortofoto-dir data/ortofotos-rejilla --ortofoto-prefijo ${B}_"
done

# 2. last.pt contra best.pt: no cuesta entrenar, solo barrer.
for B in lugo ourense coruna pontevedra; do
  barrer "$B" v7last data/cls-v7/last.pt
done

# 3. Las caches de DEM que faltan. Ya no hay barridos compitiendo.
for B in ourense coruna; do
  say "=== cache de DEM de $B ==="
  nice -n 19 .venv-gpu/bin/python scripts/laz_a_dem.py \
    --laz-dir "data/external/lidar-val-$B" --out "data/dem-cache-$B" \
    --res-m 1.0 --workers 6 >> "$LOG" 2>&1
  say "$B rc=$? teselas=$(ls data/dem-cache-$B/*.npz 2>/dev/null | wc -l)"
  .venv-gpu/bin/python scripts/verificar_dem.py \
    --laz-dir "data/external/lidar-val-$B" --dem-dir "data/dem-cache-$B" \
    --n 20 >> "$LOG" 2>&1
done

# 4. v17: cuarenta epocas. Es lo ultimo porque su hipotesis no depende de nada
#    de lo anterior — la curva de v7 se corto mientras aun mejoraba.
say "=== entrenando v17 (40 epocas) ==="
CASTROS_VRAM_FRAC=0.80 .venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v7 --out-dir data/cls-v17 \
  --head cls --encoder resnet34 --epochs 40 --batch 16 --workers 2 \
  --loss focal --focal-gamma 2.0 >> "$LOG" 2>&1
say "v17 rc=$?"
if [ -f data/cls-v17/best_castro.pt ]; then
  .venv-gpu/bin/python scripts/error_de_entrenamiento.py \
    --modelo v17 --vig data/galicia-vignettes-v7 --batch 8 >> "$LOG" 2>&1
  for B in lugo ourense coruna pontevedra; do
    barrer "$B" v17 data/cls-v17/best_castro.pt
  done
fi

say "=== resumen final con cobertura ==="
.venv-gpu/bin/python scripts/f1_con_cobertura.py >> "$LOG" 2>&1
say "### cola en serie terminada ###"
