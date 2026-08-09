#!/bin/sh
# Puntua TODOS los modelos guardados sobre el examen comun de v11p.
#
# Es la tabla que faltaba: hasta ahora cada modelo se comparaba con su propio
# examen, y v11p heredo uno reducido —los mismos positivos, `2.404` fondos menos—
# asi que su `0,8539` no era comparable con el `0,4605` de v7 hasta repuntuar v7
# sobre el mismo examen (`0,4227`).
#
# Va en CPU a proposito: el barrido tiene la GPU y el nodo solo aguanta un trabajo
# pesado. Con `nice` y un techo de memoria no compite con el.
set -u
cd "$HOME/castros" || exit 1
for m in v6 v6focal v7 v8 v9 v10 v11p; do
  [ -f "data/cls-$m/best.pt" ] || continue
  echo "===== $m ====="
  CUDA_VISIBLE_DEVICES= .venv-gpu/bin/python scripts/reevaluar_en_examen.py \
    --checkpoint "data/cls-$m/best.pt" --vig-dir data/galicia-vignettes-v11p \
    --split val 2>&1 | tail -8
done
