#!/usr/bin/env python3
"""Descarta obra moderna mirando la ortofoto, que es la mitad negativa del trabajo.

Sale de una medición del `2026-08-07`. Tras arreglar el peso de los negativos
duros con focal loss, en Pontevedra quedan `5` falsos positivos y **el `100%` es
terreno que el modelo ya vio etiquetado como negativo** y sigue sin poder apagar.
Bajando su ortofoto, **`4` de esos `5` son obra moderna inequívoca**: un núcleo
urbano, una autovía con su enlace, un polígono industrial y **la pista del
aeropuerto de Vigo**. Sus terraplenes tienen firma de parapeto en relieve, y en
imagen no hay duda posible.

Así que la ortofoto no entra como canal del modelo sino como **criba posterior**,
y eso es una decisión de coste, no de pereza: un canal exigiría bajar imagen para
las `8.600` celdas de cada bloque y reconstruir el corpus entero, mientras que
cribar solo mira los **candidatos que superan el umbral** —decenas, no miles—.
Ataca exactamente donde está medido el error y cuesta mil veces menos.

Es además lo que ya hace el humano: *«la ortofoto no ayuda a ver un castro —bajo
eucalipto no se ve nada, que es justo por lo que existe el LiDAR—; ayuda a
descartar, y descartar no exige criterio arqueológico: una cantera es una
cantera»*.

## Cómo se entrena sin etiquetar nada a mano

Ya hay dos conjuntos de coordenadas con etiqueta fiable:

- **positivos**: los castros del corpus, que son arqueología de verdad;
- **negativos**: los `534` sitios que `negativos_osm.py` sacó de OpenStreetMap
  —canteras, polígonos, campos de fútbol, enlaces de autovía—, que son obra
  moderna **por definición del mapa**, no por juicio de nadie.

Con `resnet34` de ImageNet como extractor y una regresión logística encima:
ImageNet ya sabe distinguir edificios, asfalto y naves, que es justo la
diferencia que hay que ver. Con ~`1.500` ejemplos, ajustar solo la capa final es
más robusto que reentrenar la red entera.

**Lo que esta criba NO puede hacer**, y conviene tenerlo escrito: el quinto falso
positivo de Pontevedra es un **crestón rocoso natural**, y ahí la ortofoto no
decide. En Ourense el confusor dominante es **viñedo en bancales** —agrícola y
antiguo, no moderno— y varios candidatos son indistinguibles de un castro sin
catalogar. Esta criba arregla el confusor **moderno**; los otros dos no.

Uso:
    python3 scripts/criba_ortofoto.py entrenar --salida data/criba-orto
    python3 scripts/criba_ortofoto.py aplicar --modelo data/criba-orto \\
        --pred data/sweep_val_pontevedra_v6focal.tsv --umbral 0.7
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
UA = "castros-ia (investigacion arqueologica)"
LADO_M, PX = 384.0, 224          # 224 px es la entrada nativa de resnet


def ortofoto(x, y, lado=LADO_M, px=PX, intentos=3):
    h = lado / 2.0
    q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
         "LAYERS": "OI.OrthoimageCoverage", "STYLES": "", "CRS": "EPSG:25829",
         "FORMAT": "image/jpeg", "BBOX": f"{x-h},{y-h},{x+h},{y+h}",
         "WIDTH": str(px), "HEIGHT": str(px)}
    url = WMS + "?" + urllib.parse.urlencode(q)
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = r.read()
            if d.startswith(b"\xff\xd8"):
                return d
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    return None


def a_array(jpg):
    from PIL import Image
    im = Image.open(io.BytesIO(jpg)).convert("RGB").resize((PX, PX))
    return np.asarray(im, dtype=np.uint8)


def bajar(puntos, cache: Path, etiqueta):
    """Baja y cachea en disco: el WMS es público y no se le pide dos veces."""
    from pyproj import Transformer
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)
    cache.mkdir(parents=True, exist_ok=True)
    X, y, hechos = [], [], 0
    for i, (lon, lat) in enumerate(puntos):
        f = cache / f"{etiqueta}_{i:05d}.npy"
        if f.exists():
            X.append(np.load(f)); y.append(etiqueta); continue
        jpg = ortofoto(*fwd.transform(lon, lat))
        if jpg is None:
            continue
        a = a_array(jpg)
        np.save(f, a)
        X.append(a); y.append(etiqueta); hechos += 1
        time.sleep(0.4)
        if hechos % 25 == 0:
            print(f"    {etiqueta}: {hechos} bajadas ({i+1}/{len(puntos)})",
                  flush=True)
    return X, y


def rasgos(X, dev):
    """resnet34 de ImageNet como extractor: sabe de edificios y asfalto."""
    import torch
    import torchvision.models as tvm
    net = tvm.resnet34(weights="IMAGENET1K_V1")
    net.fc = torch.nn.Identity()
    net.eval().to(dev)
    med = np.array([0.485, 0.456, 0.406], np.float32)
    des = np.array([0.229, 0.224, 0.225], np.float32)
    out = []
    with torch.no_grad():
        for i in range(0, len(X), 32):
            a = np.stack(X[i:i+32]).astype(np.float32) / 255.0
            a = (a - med) / des
            t = torch.from_numpy(a.transpose(0, 3, 1, 2)).to(dev)
            out.append(net(t).cpu().numpy())
    return np.concatenate(out)


def leer_puntos(p, col_lon="lon", col_lat="lat"):
    out = []
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            try:
                out.append((float(r[col_lon]), float(r[col_lat])))
            except (KeyError, TypeError, ValueError):
                continue
    return out


def cmd_entrenar(args):
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    args.salida.mkdir(parents=True, exist_ok=True)
    cache = args.salida / "cache"

    negs = []
    for f in sorted((RAIZ / "data").glob("negativos-osm-*.tsv")):
        negs += leer_puntos(f)
    print(f"negativos de OSM (obra moderna por definición del mapa): {len(negs)}",
          flush=True)

    idx = RAIZ / "data/galicia-vignettes-v6/index.tsv"
    pos = []
    with open(idx, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if (r.get("group") or "").strip() == "castro" and r.get("lon"):
                try:
                    pos.append((float(r["lon"]), float(r["lat"])))
                except ValueError:
                    continue
    pos = pos[:len(negs) * 2]
    print(f"castros del corpus: {len(pos)}", flush=True)

    Xn, _ = bajar(negs, cache, "moderno")
    Xp, _ = bajar(pos, cache, "castro")
    print(f"\nimágenes: {len(Xp)} castros, {len(Xn)} modernos", flush=True)
    if len(Xp) < 30 or len(Xn) < 30:
        raise SystemExit("faltan imágenes para entrenar")

    X = rasgos(Xp + Xn, dev)
    y = np.r_[np.zeros(len(Xp)), np.ones(len(Xn))]
    # Partición por bloques no, porque los negativos de OSM y los castros vienen
    # de sitios distintos por construcción; basta una partición aleatoria
    # estratificada para saber si la señal existe.
    rng = np.random.default_rng(20260807)
    o = rng.permutation(len(y))
    X, y = X[o], y[o]
    corte = int(0.75 * len(y))
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    clf = LogisticRegression(max_iter=2000, C=1.0)
    clf.fit(X[:corte], y[:corte])
    p = clf.predict_proba(X[corte:])[:, 1]
    auc = roc_auc_score(y[corte:], p)
    acc = ((p >= 0.5) == y[corte:]).mean()
    print(f"\nROC-AUC (moderno contra castro): {auc:.4f}")
    print(f"exactitud a 0.5: {acc:.4f}")
    import pickle
    (args.salida / "clf.pkl").write_bytes(pickle.dumps(clf))
    print(f"guardado: {args.salida/'clf.pkl'}")
    if auc < 0.85:
        print("\nAVISO: por debajo de 0.85 esta criba no separa lo bastante "
              "para usarla sin revisión humana.")
    return 0


def cmd_aplicar(args):
    import pickle
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    clf = pickle.loads((args.modelo / "clf.pkl").read_bytes())
    sys.path.insert(0, str(RAIZ / "scripts"))
    from detection_eval import a_metros, agrupar, leer_tsv

    pred = [p for p in leer_tsv(args.pred, ("lon", "lat", "score"))
            if "score" in p]
    for p in pred:
        p["score"] = float(p["score"])
    sel = [p for p in pred if p["score"] >= args.umbral]
    lat0 = float(np.mean([p["lat"] for p in sel]))
    px, py = a_metros([p["lon"] for p in sel], [p["lat"] for p in sel], lat0)
    import math
    grupos = agrupar(px, py, 512.0)
    cand = []
    for g in grupos:
        cx, cy = float(np.mean(px[g])), float(np.mean(py[g]))
        lon = cx / (6371000.0*math.cos(math.radians(lat0))) * 180/math.pi
        lat = cy / 6371000.0 * 180/math.pi
        cand.append((lon, lat, max(sel[i]["score"] for i in g)))
    print(f"candidatos a umbral {args.umbral}: {len(cand)}", flush=True)

    X, _ = bajar([(c[0], c[1]) for c in cand], args.modelo / "cache-aplicar",
                 "cand")
    if not X:
        raise SystemExit("no se pudo bajar ninguna ortofoto")
    p_mod = clf.predict_proba(rasgos(X, dev))[:, 1]

    out = args.salida or args.pred.with_name(args.pred.stem + "_cribado.tsv")
    n_fuera = 0
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["lon", "lat", "score", "p_moderno"])
        for (lon, lat, sc), pm in zip(cand, p_mod):
            if pm >= args.corte:
                n_fuera += 1
                continue
            w.writerow([f"{lon:.6f}", f"{lat:.6f}", f"{sc:.4f}", f"{pm:.4f}"])
    print(f"descartados como obra moderna (p >= {args.corte}): {n_fuera}")
    print(f"quedan: {len(cand)-n_fuera} en {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("entrenar")
    e.add_argument("--salida", type=Path, default=RAIZ / "data/criba-orto")
    a = sub.add_parser("aplicar")
    a.add_argument("--modelo", type=Path, default=RAIZ / "data/criba-orto")
    a.add_argument("--pred", type=Path, required=True)
    a.add_argument("--umbral", type=float, default=0.7)
    a.add_argument("--corte", type=float, default=0.5,
                   help="p(moderno) por encima de la cual se descarta")
    a.add_argument("--salida", type=Path, default=None)
    args = ap.parse_args()
    return cmd_entrenar(args) if args.cmd == "entrenar" else cmd_aplicar(args)


if __name__ == "__main__":
    raise SystemExit(main())
