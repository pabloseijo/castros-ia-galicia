#!/bin/bash
# Prueba de extremo a extremo del barrido en streaming, sin cargar al CNIG.
#
# La aritmetica de `--solo-plan` ya dice que el pico de disco baja de 952 GB a
# 45,6 GB, pero eso es una cuenta. Lo que hay que probar es el ciclo entero:
# que el halo evita las costuras, que solo se borra lo que ya no hace falta, y
# que los TSV por bloque se juntan bien.
#
# Se prueba DENTRO del bloque de Lugo, que ya esta en disco, enlazando sus
# teselas al directorio de trabajo del streaming. Asi el descargador las
# encuentra y no baja nada: solo consulta metadatos. Los enlaces se borran como
# borraria los .laz —`unlink` sobre un enlace no toca el original—.
#
# El control es que las celdas barridas en streaming den las MISMAS
# puntuaciones que el barrido normal sobre el mismo terreno. Si el halo
# estuviera mal, las celdas del borde saldrian distintas o no saldrian.
set -u
cd "$HOME/castros" || exit 1
LOG=logs/prueba_streaming.log
mkdir -p logs
say() { echo "[$(date +%F' '%H:%M)] $*" | tee -a "$LOG"; }

# La GPU esta en EXCLUSIVE_PROCESS: dos trabajos a la vez no caben, y el
# segundo no espera, falla. Hay que esperar tambien a `cadena_noche_analisis`,
# que corre `eval_checkpoint_descentrado` y tambien quiere GPU — las dos
# cadenas esperan la misma sennal y arrancarian juntas.
say "=== esperando a la GPU y al analisis de la noche ==="
while pgrep -f "train_unet_multiclass.py|sweep_grid_lidar.py|cadena_noche_analisis.sh" > /dev/null 2>&1; do sleep 60; done
sleep 10
say "GPU libre"

# Recuadro pequenno dentro de Lugo, 4x4 km aprox, en bloques de 2 km:
# obliga a varios bloques, halo entre ellos y borrado intermedio.
BB="-7.30 42.70 -7.25 42.74"
TRAB=data/streaming-prueba
rm -rf "$TRAB"
mkdir -p "$TRAB/laz"

say "=== enlazando teselas de Lugo (sin bajar nada del CNIG) ==="
N=0
for f in data/external/lidar-val-lugo/*.laz; do
  ln -sf "$(readlink -f "$f")" "$TRAB/laz/$(basename "$f")" && N=$((N+1))
done
say "enlazadas $N teselas"

say "=== plan ==="
.venv-gpu/bin/python scripts/barrer_streaming.py --bbox $BB \
  --checkpoint data/cls-v6/best.pt --nombre prueba --bloque-km 2 \
  --solo-plan >> "$LOG" 2>&1

say "=== streaming ==="
.venv-gpu/bin/python scripts/barrer_streaming.py --bbox $BB \
  --checkpoint data/cls-v6/best.pt --nombre prueba --bloque-km 2 \
  --min-libre-gb 40 >> "$LOG" 2>&1
say "streaming rc=$?"

say "=== control: el mismo terreno con el barrido normal ==="
# Rehacer los enlaces: el streaming los fue borrando, que es lo que hace.
for f in data/external/lidar-val-lugo/*.laz; do
  ln -sf "$(readlink -f "$f")" "$TRAB/laz/$(basename "$f")"
done
.venv-gpu/bin/python scripts/sweep_grid_lidar.py \
  --laz-dir "$TRAB/laz" --checkpoint data/cls-v6/best.pt \
  --out "$TRAB/control.tsv" --bbox $BB --workers 2 --batch 16 >> "$LOG" 2>&1
say "control rc=$?"

say "=== comparacion ==="
.venv-gpu/bin/python - <<'PY' >> "$LOG" 2>&1
import csv
def leer(p):
    d = {}
    for r in csv.DictReader(open(p, encoding='utf-8'), delimiter='\t'):
        d[(round(float(r['lon']), 6), round(float(r['lat']), 6))] = float(r['score'])
    return d
try:
    a = leer('data/sweep_streaming_prueba.tsv')
    b = leer('data/streaming-prueba/control.tsv')
except FileNotFoundError as e:
    print('FALTA UN FICHERO:', e); raise SystemExit(1)
comunes = set(a) & set(b)
print(f'celdas streaming: {len(a)} | celdas control: {len(b)} | comunes: {len(comunes)}')
print(f'solo en streaming: {len(set(a)-set(b))} | solo en control: {len(set(b)-set(a))}')
if comunes:
    difs = [abs(a[k]-b[k]) for k in comunes]
    peor = max(difs)
    print(f'diferencia maxima de puntuacion: {peor:.6f}')
    print('VEREDICTO:', 'IDENTICO' if peor < 1e-6 else ('CASI (float)' if peor < 1e-3 else '*** DISCREPA ***'))
if set(b) - set(a):
    print('*** el streaming PERDIO celdas que el barrido normal si puntua ***')
PY
say "=== prueba completa ==="
