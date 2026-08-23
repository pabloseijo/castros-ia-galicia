#!/bin/bash
# Cadena nocturna: para cada orden, baja LAZ, barre con la configuracion
# congelada, y borra la entrada. El disco nunca tiene mas de una orden.
#
# NO acapara el nodo a proposito: raspberri esta caida (es el DNS de la casa)
# y tumbar tambien los servicios de oval-server dejaria a Pablo sin nada.
# El barrido va con --workers 1, que es lo que la restriccion 3 del roadmap
# exige desde que tres barridos murieron por memoria.
#
# CUIDADO CON EL PATRON DE ESPERA. La primera version usaba
#   pgrep -f cdd_portugal_download
# y se colgaba para siempre, porque el propio `bash -c` que escribio este
# fichero lleva esa cadena en su linea de comandos y pgrep se encontraba a si
# mismo. Es la misma familia de fallo que el `pkill -f` que se auto-mataba por
# SSH. El patron de abajo exige el interprete delante, asi que solo casa con el
# proceso de verdad.
cd ~/castros || exit 1
L=logs/noche_portugal.log
PAT='bin/python.*cdd_portugal_download|python3 \./scripts/cdd_portugal_download'
say(){ echo "[$(date '+%Y-%m-%d %H:%M')] $*" | tee -a "$L"; }

esperar_descarga(){
  local n=0
  while pgrep -f "$PAT" >/dev/null; do
    sleep 60
    n=$((n+1))
    [ $((n % 30)) -eq 0 ] && say "    ...esperando a la descarga en curso ($((n)) min)"
    [ $n -gt 300 ] && { say "*** descarga colgada >5 h: sigo igualmente ***"; break; }
  done
}

say "=== cadena nocturna arrancada ==="
# Las 18 primeras eran la mitad MAS DENSA del plan (8,0 castros por orden
# contra 2,4 de las restantes), asi que su cifra no es extrapolable. Estas
# diez salieron AL AZAR de las 58 que quedaban, con semilla 20260823 y
# elegidas ANTES de mirar ningun resultado, para medir si el resultado
# cambia entre zona densa y zona rala.
for N in 22 27 37 38 50 58 59 67 68 75; do
  esperar_descarga

  ESPERADOS=$(awk -v n="$N" -F'\t' '$1==n && $2=="LAZ"' data/cdd-portugal-assets-full.tsv 2>/dev/null | wc -l)
  TENGO=$(ls data/entrada-portugal/$N/LAZ 2>/dev/null | wc -l)
  if [ "$TENGO" -lt "$ESPERADOS" ] || [ "$TENGO" -eq 0 ]; then
    say "--- descargando orden $N ($TENGO de $ESPERADOS) ---"
    ./scripts/cdd_portugal_download.py --orders $N --collections LAZ --workers 4 \
      >> logs/cdd_download_order$N.log 2>&1
    say "    descarga orden $N rc=$? ($(du -sh data/entrada-portugal/$N 2>/dev/null | cut -f1))"
  else
    say "--- orden $N ya descargada ($TENGO teselas) ---"
  fi

  LIBRE=$(df --output=avail -BG / | tail -1 | tr -dc 0-9)
  if [ "$LIBRE" -lt 60 ]; then
    say "*** solo quedan ${LIBRE}G libres: paro antes de llenar el disco ***"
    break
  fi

  say "--- ingiriendo orden $N ---"
  ./scripts/ingerir_portugal.sh >> logs/ingerir_portugal.log 2>&1
  say "    ingesta rc=$? | fusion: $(wc -l < data/sweep_test_portugal_${N}.tsv 2>/dev/null || echo 0) filas"
done
say "=== cadena nocturna terminada ==="
