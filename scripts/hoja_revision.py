#!/usr/bin/env python3
"""Arma la hoja de revisión de candidatos: relieve y ortofoto, lado a lado.

Es el formato con el que ya se revisó Trasancos a mano, y funcionó: de `25`
candidatos, `11` resultaron ser enlace de autovía, cantera, embalse, polígono o
urbanización, y **ninguno de los once lo cazaba el triaje morfológico**. Mirar
las dos vistas juntas descarta la mitad del trabajo sin necesidad de ser
arqueólogo — una cantera es una cantera.

Las tres vistas dicen cosas distintas y por eso van juntas:

- **Sombreado multidireccional**: cómo se ve el terreno. Una sola dirección de
  luz esconde los tramos de parapeto paralelos a ella.
- **Relieve local (LRM)**: la altura menos su media en una ventana. Quita la
  ladera y deja el movimiento de tierras.
- **Ortofoto**: para descartar. No sirve para *ver* un castro —bajo eucalipto no
  se ve nada, que es la razón de usar LiDAR— pero delata lo moderno.

La ortofoto se baja **en paralelo con hilos**: es espera de red, no cálculo, así
que lo que la acelera es la concurrencia y no los núcleos. Con un semáforo
modesto, que el WMS del IGN es un servicio público.

Uso:
    python3 scripts/hoja_revision.py --candidatos data/candidatos_ourense.tsv \\
        --relieve data/revision-ourense/relieve --out data/revision-ourense
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
UA = "castros-ia (investigacion arqueologica)"
_sem = threading.Semaphore(4)      # cortesia con un servicio publico gratuito


def ortofoto(x, y, lado=512.0, px=512, intentos=3):
    h = lado / 2.0
    q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
         "LAYERS": "OI.OrthoimageCoverage", "STYLES": "", "CRS": "EPSG:25829",
         "FORMAT": "image/jpeg", "BBOX": f"{x-h},{y-h},{x+h},{y+h}",
         "WIDTH": str(px), "HEIGHT": str(px)}
    url = WMS + "?" + urllib.parse.urlencode(q)
    for i in range(intentos):
        try:
            with _sem:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=90) as r:
                    d = r.read()
            if d.startswith(b"\xff\xd8"):
                return d
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    return None


def b64(datos, mime):
    return f"data:{mime};base64," + base64.b64encode(datos).decode()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidatos", type=Path, required=True)
    ap.add_argument("--relieve", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--titulo", default=None)
    ap.add_argument("--hilos", type=int, default=6)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    filas = list(csv.DictReader(open(args.candidatos, encoding="utf-8"),
                                delimiter="\t"))
    print(f"candidatos: {len(filas)}", flush=True)

    from pyproj import Transformer
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)
    cacheo = args.out / "ortofoto"
    cacheo.mkdir(exist_ok=True)

    def traer(i_r):
        i, r = i_r
        f = cacheo / f"{i:03d}.jpg"
        if f.exists():
            return i, f.read_bytes()
        d = ortofoto(*fwd.transform(float(r["lon"]), float(r["lat"])))
        if d:
            f.write_bytes(d)
        return i, d

    with ThreadPoolExecutor(max_workers=args.hilos) as ex:
        ortos = dict(ex.map(traer, list(enumerate(filas))))
    print(f"ortofotos: {sum(1 for v in ortos.values() if v)}/{len(filas)}",
          flush=True)

    pngs = sorted(args.relieve.glob("*.png"))
    def relieve_de(i):
        # `render_candidate_relief` nombra `cand-NN-sombra.png` y `cand-NN-lrm.png`,
        # en el mismo orden que el TSV de entrada. Se pide sombra primero porque
        # es la vista que orienta, y el LRM despues, que es la que decide.
        out = []
        for suf in ("sombra", "lrm"):
            f = args.relieve / f"cand-{i:02d}-{suf}.png"
            if f.exists():
                out.append(f)
        return out

    tarjetas = []
    for i, r in enumerate(filas):
        lon, lat, sc = float(r["lon"]), float(r["lat"]), float(r["score"])
        vistas = []
        for p in relieve_de(i):
            vistas.append(f"<img src='{b64(p.read_bytes(),'image/png')}' "
                          f"style='width:32%;border-radius:4px'>")
        if ortos.get(i):
            vistas.append(f"<img src='{b64(ortos[i],'image/jpeg')}' "
                          f"style='width:32%;border-radius:4px'>")
        tarjetas.append(f"""<div style="background:#fff;border-radius:8px;padding:12px;
margin-bottom:14px;box-shadow:0 1px 4px #0002">
<div style="font:14px system-ui;margin-bottom:8px">
<b style="font-size:17px">#{i+1}</b> &nbsp; puntuación <b>{sc:.3f}</b> &nbsp;·&nbsp;
{r.get('celdas','?')} celdas &nbsp;·&nbsp;
<a href="https://www.google.com/maps/@{lat},{lon},400m/data=!3m1!1e3"
   style="color:#2980b9">{lat:.5f}, {lon:.5f}</a> &nbsp;·&nbsp;
<a href="https://www.google.com/maps/@{lat},{lon},400m/data=!3m1!1e3">satélite</a>
</div><div style="display:flex;gap:8px">{''.join(vistas)}</div></div>""")

    tit = args.titulo or args.candidatos.stem
    html = f"""<!doctype html><meta charset=utf-8><title>Revisión: {tit}</title>
<body style="font:16px/1.6 system-ui;max-width:1200px;margin:0 auto;padding:24px;
background:#f4f6f8;color:#222">
<h1 style="margin-bottom:4px">Candidatos sin catalogar — {tit}</h1>
<p style="color:#555;margin-top:0">{len(filas)} detecciones que <b>no</b> caen sobre
ningún castro conocido ni sobre la máscara de contaminación. Ordenados por
puntuación.</p>
<p style="background:#fff;border-left:4px solid #8e44ad;padding:12px 16px;border-radius:4px">
Cada fila: <b>sombreado multidireccional</b>, <b>relieve local</b> y <b>ortofoto</b>.
Los dos primeros enseñan el movimiento de tierras —una sola dirección de luz
escondería los parapetos paralelos a ella—; el tercero sirve para <b>descartar</b>
lo moderno, no para ver el castro.<br><br>
<b>Ojo con la métrica:</b> estos son los que el sistema cuenta como
<i>falsos positivos</i>. Canedo revisó sus 40 residuales y <b>9 eran castros
inéditos</b>. Aquí no lo ha mirado nadie todavía.</p>
{''.join(tarjetas)}
</body>"""
    dest = args.out / "hoja.html"
    dest.write_text(html, encoding="utf-8")
    print(f"hoja: {dest} ({dest.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
