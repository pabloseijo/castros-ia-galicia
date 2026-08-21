#!/usr/bin/env python3
"""Los controles que hay que pasar ANTES de mirar ningun F1.

Se escribe antes de que exista el corpus a proposito. Un control que se programa
despues de ver el resultado se programa, sin querer, para no molestar.

Eran tres, los del PREREGISTRO-v11. El **cuarto se anadio el 2026-08-09**, y esa
fecha es la unica parte incomoda de este fichero: llego despues de que tres
experimentos —v11p, v13 y la descarga entera de `348 GB`— fracasaran por lo que
ahora mide en un segundo.

Los cuatro, y por que cada uno:

1. **Integridad de la particion espacial.** Los splits de este proyecto son
   bloques geograficos: si un bloque aparece a la vez en `train` y en `val`, el
   modelo ha visto el terreno donde luego se le examina. Es lo que invalido
   Trasancos, donde `86` de `93` castros estaban en `train`/`val`, y es el fallo
   que mas facil se cuela al annadir positivos nuevos.

2. **Validacion identica a la de v7.** Solo asi la comparacion mide el efecto del
   dato de entrenamiento y no un cambio de examen. Si el conjunto de validacion
   cambia, `selection_best` deja de ser comparable y la regla de cribado se cae.

3. **Precinto de Portugal.** Regla `15`. El norte de Portugal es el conjunto de
   prueba y no se mira. Cualquier viñeta al sur del paralelo de corte en un
   corpus de entrenamiento es una violacion del precinto.

4. **Confusion espacial.** Ningun positivo debe vivir en un bloque del que no
   haya nada de fondo. Si un paisaje solo aparece dentro de viñetas de castro, el
   modelo puede acertar reconociendo el sitio en vez del yacimiento — y ese atajo
   no existe en el barrido real, donde cada castro compite contra las celdas de
   su propio bloque.

Sale con codigo distinto de cero si falla cualquiera: asi una cadena puede
frenar sola en vez de entrenar sobre un corpus roto.

Uso:
    python3 scripts/controles_v11.py --nuevo data/galicia-vignettes-v11p \\
        --referencia data/galicia-vignettes-v7
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

# Frontera Galicia-Portugal por el Minno. Al sur, conjunto de prueba precintado.
# Ya no se usa una linea de latitud para el precinto: ver `control_precinto`.
LAT_PRECINTO = 41.87


def metros(a, b):
    """Distancia aproximada en metros entre dos (lat, lon)."""
    dlat = (a[0] - b[0]) * 111320.0
    dlon = (a[1] - b[1]) * 111320.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dlat, dlon)


def leer(d: Path):
    p = d / "index.tsv"
    if not p.exists():
        raise SystemExit(f"no existe {p}")
    return list(csv.DictReader(p.open(encoding="utf-8"), delimiter="\t"))


def control_particion(filas) -> bool:
    """Ningun bloque puede aparecer en mas de un split."""
    por_bloque = defaultdict(set)
    for r in filas:
        por_bloque[r.get("block", "?")].add(r.get("split", "?"))
    malos = {b: s for b, s in por_bloque.items() if len(s) > 1}
    print(f"\n[1] particion espacial: {len(por_bloque)} bloques")
    if not malos:
        print("  OK: cada bloque vive en un solo split")
        return True
    print(f"  aviso: {len(malos)} bloques en varios splits")
    for b, s in list(malos.items())[:5]:
        n = sum(1 for r in filas if r.get("block") == b)
        print(f"      bloque {b!r}: {sorted(s)}  ({n} viñetas)")

    # **Compartir bloque no es lo mismo que estar cerca.** En v7 hay `9` bloques
    # mezclados, pero al medir la distancia real solo `1` de los `7` castros de
    # O Val estaba a menos de `500 m` de entrenamiento; los demas, de `971` a
    # `1.823 m`. Un bloque de `2 km` cabe de sobra dos sitios sin relacion. Asi
    # que el veredicto lo da la distancia, no la etiqueta.
    ent, examen = [], []
    for r in filas:
        try:
            p = (float(r["lat"]), float(r["lon"]))
        except (TypeError, ValueError, KeyError):
            continue
        if r.get("split") in ("train", "val"):
            ent.append(p)
        elif (r.get("group") or "").startswith("castro"):
            examen.append((p, r.get("name", "?")))
    cerca = []
    for p, nom in examen:
        d = min((metros(p, e) for e in ent if abs(e[0]-p[0]) < 0.02), default=1e12)
        if d < 500:
            cerca.append((nom, d))
    print(f"  castros de examen a menos de 500 m de entrenamiento: "
          f"{len(cerca)} de {len(examen)}")
    for n, d in sorted(cerca, key=lambda x: x[1])[:5]:
        print(f"      {n[:38]:<40}{d:>7.0f} m")
    if cerca:
        print("  *** FALLA: hay contaminacion espacial real, no solo de etiqueta ***")
        return False
    print("  OK: mezcla de etiquetas, pero separacion real suficiente")
    return True


def control_validacion(nuevas, ref, a_proposito: str | None = None) -> bool:
    """El conjunto de validacion debe ser el mismo que el de la referencia.

    Con `a_proposito` se declara que el corpus reparte de otra forma **a
    sabiendas** —v14 lo hace, porque su razon de ser es sacar del examen la
    confusion espacial que tenia v11p—. Entonces esto baja de fallo a desviacion
    declarada: sigue imprimiendose y sigue prohibiendo comparar `selection_best`
    con versiones anteriores, pero no bloquea el entrenamiento.

    **Sin declararlo sigue siendo un fallo**, que es lo que evita el error
    facil: cambiar el reparto sin darse cuenta y creer que la nota subio.
    """
    def val_sids(filas):
        return {r["sid"] for r in filas if r.get("split") == "val"}
    a, b = val_sids(nuevas), val_sids(ref)
    print(f"\n[2] validacion identica: nuevo {len(a)} | referencia {len(b)}")
    if a == b:
        print("  OK: mismo conjunto de validacion, la comparacion es limpia")
        return True
    if a_proposito:
        print(f"  DESVIACION DECLARADA: {len(a-b)} solo en el nuevo, "
              f"{len(b-a)} solo en la referencia")
        print(f"      razon: {a_proposito}")
        print("      selection_best NO es comparable; lo que vale es el despliegue")
        return True
    print(f"  *** FALLA: {len(a-b)} solo en el nuevo, {len(b-a)} solo en la referencia ***")
    print("      selection_best NO es comparable con las versiones anteriores")
    return False


def control_confusion_espacial(filas, tope=0.10) -> bool:
    """Ningun positivo debe vivir en un bloque del que no haya nada de fondo.

    **Anadido el 2026-08-09**, y es el control que le faltaba al proyecto. v11p y
    v13 tenian el `53%` de sus positivos en bloques de los que el modelo no veia
    ni una viñeta de fondo, y en su conjunto de validacion la cifra era del
    `72%`. Eso no es una fuga —nada del examen esta en el entrenamiento— pero
    hace la tarea del examen mas facil que la del despliegue: si un paisaje solo
    aparece dentro de viñetas de castro, **basta reconocer el sitio para acertar,
    sin aprender el yacimiento**.

    En el barrido real el atajo desaparece, porque el barrido recorre todas las
    celdas del bloque, castro incluido. De ahi la contradiccion que costo tres
    experimentos entender: v11p sacaba mejor validacion que v7 (`0,72`-`0,81`
    contra `0,46`) y peor despliegue.

    En la taxonomia de Kapoor y Narayanan (`10.1016/j.patter.2023.100804`) es
    **`L3.2`**: el conjunto de evaluacion no representa la poblacion de
    despliegue. Sus positivos y sus negativos no salen de la misma poblacion.

    Se mide **por split**, porque el de `val` es el que envenena la metrica. El
    tope por defecto (`10%`) esta por encima del `3%` de v7 y muy por debajo del
    `53%` de v11p: separa lo sano de lo roto sin ser quisquilloso.

    La regla que se deriva, para quien construya corpus: **al cortar una viñeta
    de castro hay que cortar fondo de su mismo bloque.**
    """
    print("\n[4] confusion espacial: positivos sin fondo en su propio bloque")
    ok = True
    for split in ("train", "val"):
        pos, neg = Counter(), Counter()
        for r in filas:
            if (r.get("split") or "").strip() != split:
                continue
            b = (r.get("block") or "").strip()
            if (r.get("group") or "").startswith("castro"):
                pos[b] += 1
            else:
                neg[b] += 1
        total = sum(pos.values())
        if not total:
            continue
        huerfanos = sum(pos[b] for b in set(pos) - set(neg))
        frac = huerfanos / total
        marca = "OK " if frac <= tope else "***"
        print(f"  {marca} {split:<6} {huerfanos:>5}/{total:<5} ({100*frac:>3.0f}%)"
              f"   tope {100*tope:.0f}%")
        if frac > tope:
            ok = False
    if not ok:
        print("      *** FALLA: el modelo puede acertar reconociendo el paisaje ***")
        print("      corta fondo de los mismos bloques de donde salen los positivos")
    return ok


def control_precinto(filas, truth: Path, radio=300.0) -> bool:
    """Ningun castro precintado puede estar a tiro de una viñeta de entrenamiento.

    **La primera version de este control usaba una linea de latitud** y dio una
    falsa alarma: marco `45` viñetas «en Portugal» —entre ellas terreno aleatorio
    de Miranda do Douro— cuando el precinto estaba perfectamente intacto. La
    frontera politica no es el criterio; **la proximidad a la verdad precintada
    si lo es**, porque es lo unico que puede inflar la medicion final.

    El protocolo fijo `300 m` al elegir los `353`. Esto lo verifica en vez de
    creerselo.
    """
    if not truth.exists():
        print(f"\n[3] precinto: NO se puede comprobar, falta {truth}")
        return False
    sellados = []
    with truth.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                sellados.append((float(r.get("lat") or r["latitude"]),
                                 float(r.get("lon") or r["longitude"]),
                                 r.get("name", "")))
            except (TypeError, ValueError, KeyError):
                pass
    ent = []
    for r in filas:
        if r.get("split") not in ("train", "val"):
            continue
        try:
            ent.append((float(r["lat"]), float(r["lon"])))
        except (TypeError, ValueError, KeyError):
            pass
    viola = []
    for t in sellados:
        d = min((metros(t, e) for e in ent if abs(e[0]-t[0]) < 0.02), default=1e12)
        if d < radio:
            viola.append((t[2], d))
    print(f"\n[3] precinto: {len(sellados)} castros sellados contra {len(ent)} viñetas")
    if viola:
        print(f"  *** FALLA: {len(viola)} sellados a menos de {radio:.0f} m de entrenamiento ***")
        for n, d in sorted(viola, key=lambda x: x[1])[:5]:
            print(f"      {n[:38]:<40}{d:>7.0f} m")
        return False
    print(f"  OK: ninguno a menos de {radio:.0f} m; el precinto sigue cerrado")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nuevo", type=Path, required=True)
    ap.add_argument("--referencia", type=Path,
                    default=Path("data/galicia-vignettes-v7"))
    ap.add_argument(
        "--val-distinta-a-proposito", metavar="RAZON", default=None,
        help="Declara que el corpus reparte la validacion de otra forma A "
             "PROPOSITO. El control [2] sigue ejecutandose y se imprime, pero "
             "baja de fallo a desviacion declarada: lo que impide es comparar "
             "`selection_best` con versiones anteriores, no entrenar. Exige "
             "escribir la razon, que queda en la salida. Sin esto, una "
             "validacion distinta sigue siendo un fallo.")
    ap.add_argument("--precinto", type=Path,
                    default=Path("data/portugal-test_truth_limpia.tsv"))
    ap.add_argument("--tope-confusion", type=float, default=0.10,
                    help="Fraccion maxima de positivos que puede vivir en un "
                         "bloque sin nada de fondo, por split. Por defecto "
                         "`0.10`: por encima del `3%%` de v7 y muy por debajo "
                         "del `53%%` de v11p.")
    args = ap.parse_args()

    nuevas, ref = leer(args.nuevo), leer(args.referencia)
    print(f"corpus nuevo: {len(nuevas)} viñetas | referencia: {len(ref)}")

    # la dosis: cuantos positivos de entrenamiento hay de verdad
    def pos_train(f):
        return sum(1 for r in f
                   if (r.get("group") or "").startswith("castro")
                   and r.get("split") == "train")
    pn, pr = pos_train(nuevas), pos_train(ref)
    print(f"positivos en train: nuevo {pn} | referencia {pr} "
          f"| dosis x{pn/max(pr,1):.2f}")
    print(f"grupos del nuevo: {dict(Counter((r.get('group') or '').split('_')[0] for r in nuevas).most_common(6))}")

    # `all()` con una lista, no con un generador: los cuatro controles tienen que
    # ejecutarse e imprimirse aunque el primero falle. Con cortocircuito, un fallo
    # en el `[1]` esconderia el estado del precinto, que es lo que mas importa ver.
    ok = all([control_particion(nuevas),
              control_validacion(nuevas, ref, args.val_distinta_a_proposito),
              control_precinto(nuevas, args.precinto),
              control_confusion_espacial(nuevas, args.tope_confusion)])
    print("\n" + ("=" * 60))
    print("TODOS LOS CONTROLES PASAN: se puede entrenar" if ok
          else "HAY CONTROLES QUE FALLAN: NO entrenar hasta arreglarlo")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
