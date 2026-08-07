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

## Como se delinea, y de donde sale el metodo

**Transformada de Hough circular** sobre la apertura. Es lo que uso el equipo que
buscaba fortalezas vikingas en Dinamarca (`10.3390/rs11161881`): detectaron
`202.048` rasgos circulares en todo el pais y los redujeron a `199` candidatos
por propiedades geometricas. Un castro es un recinto aproximadamente circular u
oval, asi que el metodo encaja.

**El circulo ajustado es una hipotesis, no una medicion.** Se dibuja con trazo
discontinuo a proposito: dice «el recinto anda por aqui y mide esto», no «el
parapeto pasa exactamente por esta linea». Un castro rara vez es un circulo
perfecto y muchos tienen varios recintos concentricos.

## La cautela sobre la posicion

El barrido pone una celda cada `256 m`, asi que **el centro de una deteccion
puede estar hasta `128 m` del centro real** — medido en el Castro do Coto do
Mosteiro, donde el desfase fue de `104 m`. Por eso la ficha centra la ventana en
el **circulo ajustado** cuando Hough encuentra uno, y no en la deteccion: el
ajuste corrige buena parte de ese error.

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

    filas = list(csv.DictReader(open(args.candidatos, encoding="utf-8"),
                                delimiter="\t"))
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
            j = int(np.nanargmax(perf))
            radio_pico = float(rs[j])
            contraste = float((perf[j] - np.nanmedian(perf))
                              / (np.nanstd(perf) + 1e-9))

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
            axes[3].add_patch(Circle((cxm, cym), radio_pico, fill=False,
                                     color="red", lw=1.6, ls=":"))
            axes[3].plot(cxm, cym, "x", color="cyan", ms=9, mew=2)
            axes[3].text(cxm, cym - radio_pico - 18,
                         f"r={radio_pico:.0f} m  (contraste {contraste:.2f})",
                         color="red", ha="center", fontsize=9)

            axes[4].plot(rs, perf, "-", color="#333", lw=1.6)
            axes[4].axvline(radio_pico, color="red", ls=":", lw=1.4)
            axes[4].set_title("perfil radial de apertura", fontsize=11)
            axes[4].set_xlabel("radio (m)", fontsize=9)
            axes[4].set_ylabel("apertura media del anillo", fontsize=9)
            axes[4].tick_params(labelsize=8)
            axes[4].grid(alpha=0.3)

            sub = (f"puntuación del modelo {float(r['score']):.3f}  ·  "
                   f"{float(r['lat']):.5f}, {float(r['lon']):.5f}  ·  "
                   f"ventana {L:.0f} m")
            sub += (f"  ·  pico del perfil a r={radio_pico:.0f} m "
                    f"(contraste {contraste:.2f})")
            fig.suptitle(f"Candidato {c['id']+1} — {args.candidatos.stem}\n{sub}",
                         fontsize=12)
            fig.text(0.5, 0.015,
                     "x cian: centro de la deteccion (rejilla de 256 m: error "
                     "posicional de hasta 128 m, medido 104 m en el Coto do "
                     "Mosteiro)   |   circulo rojo punteado: radio del maximo "
                     "del perfil radial, que es una LECTURA y no una "
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
                            "score": r["score"],
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
