"""v8 debe ser v7 con un canal mas: mismas filas, mismos grupos, mismos splits."""
import collections
import csv


def resumen(p):
    r = list(csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"))
    return (len(r),
            collections.Counter(x["group"] for x in r),
            collections.Counter(x["split"] for x in r),
            {x["sid"] for x in r})


n7, g7, s7, i7 = resumen("data/galicia-vignettes-v7/index.tsv")
n8, g8, s8, i8 = resumen("data/galicia-vignettes-v8/index.tsv")
print("filas:   v7=%d  v8=%d  ->  %s" % (n7, n8, "IGUAL" if n7 == n8 else "DISTINTO"))
print("sid:     %s" % ("mismo conjunto" if i7 == i8 else
                       "DISTINTOS (%d solo en v7, %d solo en v8)"
                       % (len(i7 - i8), len(i8 - i7))))
print("splits:  %s   %s" % ("iguales" if s7 == s8 else "DISTINTOS", dict(s8)))
print("grupos:  %s" % ("iguales" if g7 == g8 else "DISTINTOS"))
if g7 != g8:
    for k in sorted(set(g7) | set(g8)):
        if g7.get(k) != g8.get(k):
            print("   %-26s v7=%s  v8=%s" % (k, g7.get(k), g8.get(k)))
else:
    print("   " + ", ".join("%s=%d" % (k, v) for k, v in g8.most_common(6)))
print()
if n7 == n8 and i7 == i8 and s7 == s8 and g7 == g8:
    print("La unica variable que cambia entre v7 y v8 es el numero de canales.")
else:
    print("*** ATENCION: la comparacion v7/v8 NO mide solo el canal ***")
