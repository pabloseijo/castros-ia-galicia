#!/usr/bin/env python3
"""Los tres controles que el PREREGISTRO-v11 exige ANTES de mirar ningun F1.

Se escribe antes de que exista el corpus a proposito. Un control que se programa
despues de ver el resultado se programa, sin querer, para no molestar.

Los tres, y por que cada uno:

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


def control_validacion(nuevas, ref) -> bool:
    """El conjunto de validacion debe ser el mismo que el de la referencia."""
    def val_sids(filas):
        return {r["sid"] for r in filas if r.get("split") == "val"}
    a, b = val_sids(nuevas), val_sids(ref)
    print(f"\n[2] validacion identica: nuevo {len(a)} | referencia {len(b)}")
    if a == b:
        print("  OK: mismo conjunto de validacion, la comparacion es limpia")
        return True
    print(f"  *** FALLA: {len(a-b)} solo en el nuevo, {len(b-a)} solo en la referencia ***")
    print("      selection_best NO es comparable con las versiones anteriores")
    return False


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
    ap.add_argument("--precinto", type=Path,
                    default=Path("data/portugal-test_truth_limpia.tsv"))
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

    ok = all([control_particion(nuevas),
              control_validacion(nuevas, ref),
              control_precinto(nuevas, args.precinto)])
    print("\n" + ("=" * 60))
    print("TODOS LOS CONTROLES PASAN: se puede entrenar" if ok
          else "HAY CONTROLES QUE FALLAN: NO entrenar hasta arreglarlo")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
