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
# El control NO puede ser «las mismas puntuaciones celda a celda», y conviene
# saber por que: `sweep_grid_lidar` ancla su rejilla en la esquina del bbox que
# recibe, y en streaming cada bloque recibe el suyo. Las dos rejillas quedan
# desfasadas y NINGUNA celda cae en el mismo sitio. La primera version de esta
# prueba comparaba por coordenada exacta, saco «0 comunes» y concluyo que el
# streaming perdia celdas: la conclusion era falsa y la comparacion, imposible
# por construccion.
#
# Lo que si se puede comprobar, y es lo que importa, es la COBERTURA: que cada
# celda del barrido normal tenga una del streaming a menos de un paso (256 m).
# Si el halo estuviera mal, las celdas del borde de bloque no se puntuarian y
# apareceria un hueco.
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
import csv, math
import numpy as np
def leer(p):
    xs, ys, sc = [], [], []
    for r in csv.DictReader(open(p, encoding='utf-8'), delimiter='\t'):
        xs.append(float(r['lon'])); ys.append(float(r['lat']))
        sc.append(float(r['score']))
    return np.array(xs), np.array(ys), np.array(sc)
try:
    ax, ay, asc = leer('data/sweep_streaming_prueba.tsv')
    bx, by, bsc = leer('data/streaming-prueba/control.tsv')
except FileNotFoundError as e:
    print('FALTA UN FICHERO:', e); raise SystemExit(1)
k = 111320.0
lat0 = float(np.mean(by))
m = lambda x, y: (x * k * math.cos(math.radians(lat0)), y * k)
AX, AY = m(ax, ay); BX, BY = m(bx, by)
d = np.array([np.hypot(AX - BX[i], AY - BY[i]).min() for i in range(len(BX))])
print(f'celdas streaming {len(ax)} | control {len(bx)}')
print('distancia de cada celda del CONTROL a la mas proxima del STREAMING:')
print(f'  mediana {np.median(d):.1f} m | p95 {np.percentile(d,95):.1f} m | max {d.max():.1f} m')
cob = (d <= 256).mean()
print(f'  cubiertas a menos de un paso (256 m): {(d<=256).sum()}/{len(d)} ({100*cob:.0f}%)')
print('VEREDICTO:', 'COBERTURA COMPLETA' if cob == 1.0
      else f'*** HUECOS: {(d>256).sum()} celdas del control sin vecino ***')
PY
say "=== prueba completa ==="
