#!/usr/bin/env python3
"""Baja la ortofoto del PNOA de unos puntos y arma una hoja de contacto.

Existe para responder, antes de construir nada, la pregunta que quedó abierta la
noche del `2026-08-07`: **¿la ortofoto distingue lo que el relieve no puede?**

El estado es este. Focal loss redujo los falsos positivos de Pontevedra de `26`
a `5`, y de esos `5` **el `100%` es terreno que el modelo ya había visto
etiquetado como negativo** y sigue sin poder apagar. No es falta de ejemplos ni
mal peso —las dos cosas se probaron y se midieron—: desde el relieve solo, esos
confusores no se distinguen de un castro.

La ortofoto es la única hipótesis que queda, y **ya tiene apoyo empírico propio**:
mirando a ojo, `11` de `25` candidatos de Trasancos resultaron ser enlace de
autovía, cantera, embalse, polígono o urbanización, y **ninguno de los once lo
cazaba el triaje morfológico**. Lo que falta es comprobarlo justo sobre los que
sobreviven a focal loss, que son los difíciles de verdad.

Si esos `5` se ven modernos a simple vista, el canal de ortofoto arregla
exactamente lo que queda y merece el trabajo. Si se ven como campo abierto
indistinguible, la ortofoto tampoco es la respuesta y **hay que saberlo antes de
reescribir el corpus**, no después.

**Ojo con lo que la ortofoto no hace.** No sirve para *ver* un castro —bajo
eucalipto no se ve nada, que es justo la razón de usar LiDAR—. Sirve para
**descartar**, y descartar no exige criterio arqueológico: una cantera es una
cantera.

Uso:
    python3 scripts/ortofoto_candidatos.py \\
        --pred data/sweep_val_pontevedra_v6focal.tsv \\
        --truth data/pontevedra_truth_limpia.tsv \\
        --mascara data/pontevedra_mascara_train.tsv \\
        --umbral 0.8 --salida reports/ortofoto-pontevedra
"""
from __future__ import annotations

import argparse
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detection_eval import a_metros, agrupar, leer_tsv  # noqa: E402

WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
UA = "castros-ia (investigacion arqueologica)"


def ortofoto(x, y, lado_m=512.0, px=512):
    """Recorte cuadrado de ortofoto centrado en un punto UTM29."""
    h = lado_m / 2.0
    q = {
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
        "LAYERS": "OI.OrthoimageCoverage", "STYLES": "",
        "CRS": "EPSG:25829", "FORMAT": "image/jpeg",
        "BBOX": f"{x-h},{y-h},{x+h},{y+h}",
        "WIDTH": str(px), "HEIGHT": str(px),
    }
    req = urllib.request.Request(WMS + "?" + urllib.parse.urlencode(q),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        datos = r.read()
    if not datos.startswith(b"\xff\xd8"):        # no es JPEG: el WMS dio error
        raise RuntimeError(datos[:200].decode("utf-8", "replace"))
    return datos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--mascara", type=Path, default=None)
    ap.add_argument("--umbral", type=float, default=0.8)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--lado-m", type=float, default=512.0)
    ap.add_argument("--max-fp", type=int, default=12)
    ap.add_argument("--max-tp", type=int, default=6,
                    help="aciertos, como control: hay que poder distinguirlos")
    args = ap.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True)

    pred = [p for p in leer_tsv(args.pred, ("lon", "lat", "score")) if "score" in p]
    for p in pred:
        p["score"] = float(p["score"])
    truth = leer_tsv(args.truth)
    mascara = leer_tsv(args.mascara) if args.mascara else []

    lat0 = float(np.mean([t["lat"] for t in truth]))
    sel = [p for p in pred if p["score"] >= args.umbral]
    px_, py_ = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
    grupos = agrupar(px_, py_, 512.0)
    tx, ty = a_metros([t["lon"] for t in truth], [t["lat"] for t in truth], lat0)
    if mascara:
        mx, my = a_metros([m["lon"] for m in mascara],
                          [m["lat"] for m in mascara], lat0)

    from pyproj import Transformer
    autm = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)

    fps, tps = [], []
    for g in grupos:
        cx, cy = float(np.mean(px_[g])), float(np.mean(py_[g]))
        sc = max(sel[i]["score"] for i in g)
        lon = cx / (6371000.0 * math.cos(math.radians(lat0))) * 180 / math.pi
        lat = cy / 6371000.0 * 180 / math.pi
        d_t = float(np.hypot(tx - cx, ty - cy).min())
        if d_t <= 500:
            tps.append((sc, lon, lat))
            continue
        if mascara and float(np.hypot(mx - cx, my - cy).min()) <= 500:
            continue
        fps.append((sc, lon, lat))

    fps.sort(key=lambda r: -r[0])
    tps.sort(key=lambda r: -r[0])
    lote = ([("FP", s, lo, la) for s, lo, la in fps[:args.max_fp]]
            + [("TP", s, lo, la) for s, lo, la in tps[:args.max_tp]])
    print(f"falsos positivos: {len(fps)} (se bajan {min(len(fps), args.max_fp)}) | "
          f"aciertos de control: {min(len(tps), args.max_tp)}", flush=True)

    filas = []
    for i, (clase, sc, lon, lat) in enumerate(lote):
        x, y = autm.transform(lon, lat)
        nombre = f"{clase}_{i:02d}_s{sc:.2f}.jpg"
        try:
            (args.salida / nombre).write_bytes(
                ortofoto(x, y, args.lado_m))
            print(f"  {nombre}  ({lat:.5f}, {lon:.5f})", flush=True)
            filas.append((clase, sc, lon, lat, nombre))
        except Exception as exc:
            print(f"  FALLO {nombre}: {str(exc)[:120]}", flush=True)
        time.sleep(1.0)          # cortesia con un servicio publico

    html = args.salida / "hoja.html"
    trozos = ["<h1>Ortofoto de los candidatos que el relieve no sabe descartar</h1>",
              f"<p>Umbral {args.umbral}. Recuadro de {args.lado_m:.0f} m. "
              "<b>FP</b> = el modelo lo marca y no hay castro catalogado. "
              "<b>TP</b> = acierto, va de control.</p>",
              "<p>La pregunta: <b>¿se ve a simple vista que los FP son obra "
              "moderna?</b> Si sí, el canal de ortofoto arregla justo lo que "
              "queda. Si se ven como campo indistinguible, tampoco es la "
              "respuesta.</p>",
              "<div style='display:flex;flex-wrap:wrap;gap:12px'>"]
    for clase, sc, lon, lat, nombre in filas:
        color = "#c33" if clase == "FP" else "#3a3"
        trozos.append(
            f"<figure style='margin:0'><img src='{nombre}' width='320'>"
            f"<figcaption style='font:13px sans-serif'>"
            f"<b style='color:{color}'>{clase}</b> score {sc:.2f}<br>"
            f"<a href='https://www.google.com/maps/@{lat},{lon},300m/data=!3m1!1e3'>"
            f"{lat:.5f}, {lon:.5f}</a></figcaption></figure>")
    trozos.append("</div>")
    html.write_text("\n".join(trozos), encoding="utf-8")
    print(f"\nhoja de contacto: {html}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
