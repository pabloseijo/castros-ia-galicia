#!/usr/bin/env python3
"""Ficha publicable de un candidato: cuatro vistas, el recinto delineado y escala.

Lo que el proyecto entregaba hasta ahora era una coordenada y una puntuacion. Eso
sirve para ordenar una cola, pero no para un paper ni para que un arqueologo se
haga una idea sin abrir el SIG. Esto produce la figura que si sirve.

## Por que cuatro paneles y no uno

Cada visualizacion ensena algo que las otras esconden, y la practica del campo es
mostrarlas juntas:

- **Sombreado multidireccional** — como se ve el terreno. Una sola direccion de
  luz esconde los tramos de parapeto paralelos a ella.
- **Apertura** (Doneus 2013, `10.3390/rs5126427`) — sin sesgo direccional y
  resaltando alto y bajo a la vez, o sea caballon **y** foso. Es de donde se
  saca la delineacion.
- **Ortofoto** — para descartar lo moderno. No ensena el castro bajo eucalipto,
  pero delata una cantera.
- **Interpretacion** — el recinto dibujado sobre el sombreado.

## Como se delinea, y por que NO se dibuja un circulo

**Con un perfil radial de la apertura, no con Hough.** La transformada de Hough
circular se probo —es lo que uso el equipo de las fortalezas vikingas danesas,
`10.3390/rs11161881`— y **no sirve aqui**: sus objetivos son circunferencias casi
perfectas de trazado limpio y un castro gallego no lo es. Medido sobre el Castro
do Coto do Mosteiro, cuyo recinto se ve a simple vista y mide `~170 m`, Hough
devolvia siempre el radio **minimo** del rango (`30-34 m`) y a `100-170 m` del
centro, incluso centrando la ventana en el yacimiento: el acumulador favorece los
circulos pequenos, que la textura del monte produce a montones.

El perfil radial aprovecha lo que este problema **si** da —la posicion
aproximada ya la tiene el barrido, y lo que falta es el radio—: un parapeto con
su foso deja un maximo del perfil a la distancia del anillo.

**Y no se dibuja ninguna circunferencia, a proposito.** El perfil no esta
calibrado: sobre `4` castros conocidos el contraste del pico va de `2,21` a
`2,77` y sobre `3` falsos positivos de `0,79` a `2,03`, o sea **se solapan**. Con
esas muestras no hay umbral defendible, asi que la ficha **ensena el perfil** y
deja que lo lea quien mire. Una circunferencia dibujada se leeria como una
medicion, y aqui no la hay.

## La cautela sobre la posicion

El barrido pone una celda cada `256 m`, asi que **el centro de una deteccion
puede estar hasta `128 m` del centro real** — medido en el Castro do Coto do
Mosteiro, donde el desfase fue de `104 m`. Por eso la ventana se dibuja amplia
—`600 m` de lado— y el perfil radial se mide desde el centro de la deteccion: si
el recinto esta descentrado, su anillo aparece igual en el perfil, solo que mas
ancho.

Uso:
    python3 scripts/ficha_candidato.py --candidatos data/candidatos_ourense.tsv \\
        --laz-dir data/external/lidar-val-ourense --out reports/fichas-ourense
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
UA = "castros-ia (investigacion arqueologica)"
# Radios plausibles de un recinto castrexo: los medidos en el proyecto van de
# 38 a 83 m (p10-p90), y se abre un poco el rango por arriba y por abajo.
RADIOS_M = (30, 110)


def ortofoto(x, y, lado, px=600):
    h = lado / 2.0
    q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
         "LAYERS": "OI.OrthoimageCoverage", "STYLES": "", "CRS": "EPSG:25829",
         "FORMAT": "image/jpeg", "BBOX": f"{x-h},{y-h},{x+h},{y+h}",
         "WIDTH": str(px), "HEIGHT": str(px)}
    try:
        req = urllib.request.Request(WMS + "?" + urllib.parse.urlencode(q),
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as r:
            d = r.read()
        if d.startswith(b"\xff\xd8"):
            from PIL import Image
            return np.asarray(Image.open(io.BytesIO(d)).convert("RGB"))
    except Exception:
        pass
    return None


def sombreado(dem, res, direcciones=(315, 45, 135, 225), altura=35.0):
    """Media de varios azimuts. Uno solo esconde lo paralelo a la luz."""
    gy, gx = np.gradient(dem.astype(np.float64), res)
    pend = np.arctan(np.hypot(gx, gy))
    asp = np.arctan2(-gx, gy)
    z = np.radians(altura)
    acc = np.zeros_like(dem, dtype=np.float64)
    for az in direcciones:
        a = np.radians(360.0 - az + 90.0)
        acc += (np.sin(z) * np.cos(pend)
                + np.cos(z) * np.sin(pend) * np.cos(a - asp))
    return np.clip(acc / len(direcciones), 0, 1)


def perfil_radial(apert, res, rmax_m=140.0, ancho_m=3.0):
    """Apertura media por anillo desde el centro. Devuelve `(radios, perfil)`.

    Sustituye a la transformada de Hough, **que se probó y no sirve aquí**. Los
    daneses la usaron con éxito para fortalezas vikingas (`10.3390/rs11161881`),
    pero sus objetivos son circunferencias casi perfectas de trazado limpio y un
    castro gallego no lo es. Medido sobre el Castro do Coto do Mosteiro, cuyo
    recinto se ve a simple vista y mide `~170 m`: Hough devolvía siempre el radio
    **mínimo** del rango (`30-34 m`) y a `100-170 m` del centro, incluso
    centrando la ventana en el yacimiento. El acumulador favorece los círculos
    pequeños, que la textura del monte produce a montones.

    El perfil radial aprovecha lo que este problema **sí** da: la posición
    aproximada ya la tiene el barrido, y lo que falta es el radio. Un parapeto
    con su foso deja un máximo del perfil a la distancia del anillo.

    **No está calibrado y por eso no decide nada.** Sobre `4` castros conocidos
    el contraste del pico va de `2,21` a `2,77`, y sobre `3` falsos positivos
    identificados a ojo va de `0,79` a `2,03`: **se solapan**. Con esas muestras
    no hay umbral defendible, así que la ficha **enseña el perfil** y deja que
    lo lea quien mire, en vez de dibujar una circunferencia que se leería como
    una medida.
    """
    from openness import apertura
    pos, neg = apertura(apert, res, 30.0, 8) if apert.ndim == 2 else (None, None)
    v = pos - neg
    n = v.shape[0]
    c = (n - 1) / 2.0
    yy, xx = np.ogrid[:n, :n]
    d = np.hypot(yy - c, xx - c) * res
    rs = np.arange(6.0, rmax_m, 2.0)
    perf = np.array([np.nanmean(v[(d >= r - ancho_m) & (d < r + ancho_m)])
                     for r in rs])
    return rs, perf, v


def pico_del_perfil(rs, perf, rmin_m=25.0):
    """Radio del anillo: **maximo LOCAL**, no el global. Devuelve `(j, contraste)`.

    **El maximo global cae siempre en el radio mas pequenno**, y no por casualidad:
    la apertura decae desde la cima porque el centro de un alto es, por
    definicion, lo mas abierto de su entorno. Buscar el maximo global es medir esa
    tendencia, no el anillo.

    Es exactamente el sesgo que refuto a la transformada de Hough aqui —devolvia
    siempre el radio minimo del rango— y sobrevivio al cambio de metodo. Se vio
    en la primera ficha mirada: el candidato 1 de Ourense declaraba `r=6 m`
    —seis metros de radio, que no es un recinto de nada— cuando en la curva se
    ve un segundo maximo hacia los `57 m`.

    Asi que se buscan **maximos locales** —puntos mas altos que sus dos vecinos—
    a partir de `rmin_m`. El suelo esta en `25 m` porque un recinto castrexo con
    parapeto no baja de ahi: los castros gallegos van de `50` a `200 m` de
    diametro, y el Coto do Mosteiro, medido a ojo sobre el sombreado, ronda los
    `170 m`.

    Si no hay ningun maximo local, **se devuelve `None`** en vez de inventarse
    uno. «No se ve anillo» es una lectura util y es la honesta.
    """
    r = np.asarray(rs, float)
    y = np.asarray(perf, float)
    ok = r >= rmin_m
    if ok.sum() < 3:
        return None, float("nan")
    idx = np.where(ok)[0]
    locales = [i for i in idx[1:-1]
               if np.isfinite(y[i]) and y[i] > y[i-1] and y[i] > y[i+1]]
    if not locales:
        return None, float("nan")
    j = max(locales, key=lambda i: y[i])
    # Contraste contra el tramo evaluado, no contra el perfil entero: incluir el
    # arranque cerca del centro infla el numero en todos los casos por igual.
    tramo = y[idx]
    contraste = float((y[j] - np.nanmedian(tramo)) / (np.nanstd(tramo) + 1e-9))
    return int(j), contraste


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidatos", type=Path, required=True)
    ap.add_argument("--laz-dir", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lado-m", type=float, default=600.0)
    ap.add_argument("--res-m", type=float, default=1.0)
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--sin-orto", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    import laspy
    from build_trasancos_vignettes import (grid_from_points,
                                           group_samples_by_tiles,
                                           lonlat_to_utm29)
    from openness import apertura

    # **Acepta TSV y CSV.** Los barridos y `extraer_candidatos.py` escriben con
    # tabulador; `verificar_candidatos.py` escribe el triaje con coma. Leyendo
    # siempre como TSV, un fichero de triaje daba una sola columna llamada
    # «n,lon,lat,...» y reventaba con `KeyError: 'lon'`. Se decide por la
    # cabecera, que es dato y no suposicion.
    with open(args.candidatos, encoding="utf-8") as fh:
        cabecera = fh.readline()
    sep = "\t" if cabecera.count("\t") >= cabecera.count(",") else ","
    filas = list(csv.DictReader(open(args.candidatos, encoding="utf-8"),
                                delimiter=sep))
    def col(r, *nombres, d=""):
        """Primera columna que exista, de varios nombres posibles.

        `extraer_candidatos.py` llama `score` a la puntuacion del modelo y
        `verificar_candidatos.py` la llama `score_modelo`. La ficha tiene que
        poder dibujar las dos salidas, que es justo el caso de uso: se mira la
        cruda para explorar y la triada para revisar.
        """
        for n in nombres:
            if r.get(n) not in (None, ""):
                return r[n]
        return d

    if not filas or "lon" not in filas[0]:
        raise SystemExit(f"{args.candidatos}: no encuentro columnas lon/lat. "
                         f"Cabecera leida con separador {sep!r}: "
                         f"{list(filas[0]) if filas else '(vacio)'}")
    if args.max:
        filas = filas[:args.max]
    L, res = args.lado_m, args.res_m
    celdas = []
    for i, r in enumerate(filas):
        x, y = lonlat_to_utm29(float(r["lon"]), float(r["lat"]))
        celdas.append({"id": i, "x": x, "y": y,
                       "lon": float(r["lon"]), "lat": float(r["lat"])})
    tiles = sorted(str(p) for d in args.laz_dir for p in Path(d).glob("*.laz"))
    grupos, _ = group_samples_by_tiles(celdas, tiles, L + 40)

    resumen = []
    for tp, cs in grupos.items():
        xs, ys, zs = [], [], []
        for t in tp:
            try:
                with laspy.open(t) as fh:
                    for p in fh.chunk_iterator(4_000_000):
                        k = np.asarray(p.classification) == 2
                        if not k.any():
                            continue
                        xs.append(np.asarray(p.x)[k].astype(np.float32))
                        ys.append(np.asarray(p.y)[k].astype(np.float32))
                        zs.append(np.asarray(p.z)[k].astype(np.float32))
            except Exception:
                continue
        if not xs:
            continue
        X = np.concatenate(xs); Y = np.concatenate(ys); Z = np.concatenate(zs)
        for c in cs:
            h = L / 2.0
            b = (c["x"]-h, c["y"]-h, c["x"]+h, c["y"]+h)
            m = (X >= b[0]) & (X <= b[2]) & (Y >= b[1]) & (Y <= b[3])
            if m.sum() < 5000:
                continue
            dem = grid_from_points(X[m], Y[m], Z[m], b, res)
            if dem is None or np.ndim(dem) != 2:
                continue
            r = filas[c["id"]]
            sh = sombreado(dem, res)
            rs, perf, ap_ = perfil_radial(dem, res)
            j, contraste = pico_del_perfil(rs, perf)
            radio_pico = float(rs[j]) if j is not None else float("nan")

            orto = None if args.sin_orto else ortofoto(c["x"], c["y"], L)
            if not args.sin_orto:
                time.sleep(0.5)

            fig, axes = plt.subplots(1, 5, figsize=(23, 5.2))
            n = dem.shape[0]
            ext = [0, n*res, 0, n*res]
            for ax_, img, tit, cmap in (
                    (axes[0], sh, "sombreado multidireccional", "gray"),
                    (axes[1], ap_, "apertura (caballón y foso)", "gray"),
                    (axes[2], orto, "ortofoto PNOA", None),
                    (axes[3], sh, "interpretación", "gray")):
                if img is None:
                    ax_.text(0.5, 0.5, "sin ortofoto", ha="center",
                             transform=ax_.transAxes)
                    ax_.set_xticks([]); ax_.set_yticks([])
                else:
                    ax_.imshow(img, cmap=cmap, extent=ext, origin="upper")
                ax_.set_title(tit, fontsize=11)
                ax_.set_xticks([]); ax_.set_yticks([])

            # escala de 100 m en el primer panel
            axes[0].plot([20, 120], [25, 25], "-", color="yellow", lw=3)
            axes[0].text(22, 38, "100 m", color="yellow", fontsize=10)
            axes[0].annotate("N", xy=(n*res-35, n*res-70), xytext=(n*res-35, n*res-25),
                             color="yellow", ha="center", fontsize=12,
                             arrowprops=dict(arrowstyle="->", color="yellow"))

            # El anillo del pico se dibuja SIEMPRE con trazo fino y punteado, y
            # etiquetado con su contraste, porque es una lectura del perfil y no
            # una delineacion. Quien mire decide si se lo cree.
            cxm = cym = n * res / 2
            axes[3].plot(cxm, cym, "x", color="cyan", ms=9, mew=2)
            if j is not None:
                axes[3].add_patch(Circle((cxm, cym), radio_pico, fill=False,
                                         color="red", lw=1.6, ls=":"))
                axes[3].text(cxm, cym - radio_pico - 18,
                             f"r={radio_pico:.0f} m  (contraste {contraste:.2f})",
                             color="red", ha="center", fontsize=9)
            else:
                # **«No se ve anillo» es una lectura, y de las utiles.** Antes se
                # dibujaba igual el maximo global, que caia siempre en el radio
                # minimo; ahora, si no hay maximo local, se dice.
                axes[3].text(cxm, cym * 0.25, "sin anillo detectable",
                             color="red", ha="center", fontsize=10)

            axes[4].plot(rs, perf, "-", color="#333", lw=1.6)
            if j is not None:
                axes[4].axvline(radio_pico, color="red", ls=":", lw=1.4)
            axes[4].set_title("perfil radial de apertura", fontsize=11)
            axes[4].set_xlabel("radio (m)", fontsize=9)
            axes[4].set_ylabel("apertura media del anillo", fontsize=9)
            axes[4].tick_params(labelsize=8)
            axes[4].grid(alpha=0.3)

            sub = (f"puntuación del modelo {float(col(r, 'score', 'score_modelo', d=0)):.3f}  ·  "
                   f"{float(r['lat']):.5f}, {float(r['lon']):.5f}  ·  "
                   f"ventana {L:.0f} m")
            sub += (f"  ·  anillo a r={radio_pico:.0f} m "
                    f"(contraste {contraste:.2f})" if j is not None
                    else "  ·  sin anillo detectable")
            fig.suptitle(f"Candidato {c['id']+1} — {args.candidatos.stem}\n{sub}",
                         fontsize=12)
            fig.text(0.5, 0.015,
                     "x cian: centro de la deteccion (rejilla de 256 m: error "
                     "posicional de hasta 128 m, medido 104 m en el Coto do "
                     "Mosteiro)   |   circulo rojo punteado: primer maximo LOCAL "
                     "del perfil a partir de 25 m, que es una LECTURA y no una "
                     "delineacion. Sin calibrar: sobre 4 castros el contraste "
                     "va de 2,2 a 2,8 y sobre 3 falsos positivos de 0,8 a 2,0, "
                     "y se solapan. El perfil entero esta en el ultimo panel: "
                     "miralo antes de creerte el pico.",
                     ha="center", fontsize=8.5, color="#444")
            fig.tight_layout(rect=[0, 0.04, 1, 0.90])
            dest = args.out / f"cand-{c['id']+1:03d}.png"
            fig.savefig(dest, dpi=110)
            plt.close(fig)
            resumen.append({"n": c["id"]+1, "lon": r["lon"], "lat": r["lat"],
                            "score": col(r, "score", "score_modelo"),
                            "radio_pico_m": f"{radio_pico:.0f}",
                            "contraste": f"{contraste:.2f}",
                            "ficha": dest.name})
            print(f"  {dest.name} | r={radio_pico:.0f} m contraste "
                  f"{contraste:.2f}", flush=True)
        del X, Y, Z

    if resumen:
        with open(args.out / "resumen.csv", "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(resumen[0].keys()))
            w.writeheader(); w.writerows(resumen)
        print(f"\n{len(resumen)} fichas en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
