#!/usr/bin/env python3
"""Revisa las fichas con un modelo de visión local. El orquestador lee el TSV.

**Por qué existe** (regla `17` de `CLAUDE.md`). Mirar `54` fichas una a una cuesta
como leer `54` páginas de texto, y el criterio que se aplica en cada una cabe en
un prompt. Si cabe en un prompt, va a un modelo local: yo escribo el criterio una
vez, el modelo lo aplica a las `N` fichas, y solo se lee la tabla y las
discrepancias.

**Qué mira, y por qué esas cosas.** El criterio sale de revisar `25` fichas a
mano el `2026-08-08`, donde aparecieron cuatro clases de falso positivo con firma
visual clara y una lección de método:

- **Aterrazamiento**: líneas paralelas siguiendo la curva de nivel. El confusor
  dominante de Ourense (O Ribeiro).
- **Parcelario agrícola**: polígonos rectos con lindes y setos.
- **Obra moderna**: cantera, desmonte, enlace de autovía, cierre de finca.
- **Cima natural**: la ruptura de pendiente coincide con el borde del propio alto.
- Y lo que **sí** es señal: **plataforma llana con borde envolvente cerrado**, en
  monte, destacando de lo que la rodea.

**Lo que el modelo NO decide.** No dice «es un castro». Describe lo que ve en
categorías cerradas y da una confianza. La decisión sigue siendo humana — un
modelo pequeño clasifica bien y razona mal.

**Cautela sobre la medida.** El acuerdo con la revisión manual se mide sobre las
`25` fichas ya revisadas antes de fiarse de las otras `29`. Si el acuerdo es
pobre, el TSV vale como descripción y no como clasificación, y se dice.

Uso:
    python3 scripts/revisar_fichas_local.py --fichas data/fichas-v7g \\
        --out data/revision_local.tsv --modelo qwen2.5vl:7b
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import subprocess
import time
from pathlib import Path

PROMPT = """Analiza esta figura de análisis LiDAR de un posible yacimiento arqueológico.
Tiene 5 paneles: sombreado del terreno, apertura topográfica, ortofoto aérea,
interpretación con un círculo rojo, y un perfil radial.

Responde SOLO con un objeto JSON, sin texto alrededor, con estas claves exactas:

{"recinto_cerrado": "si|parcial|no",
 "aterrazamiento": "si|no",
 "parcelario_agricola": "si|no",
 "obra_moderna": "cantera|desmonte|autovia|edificacion|finca_cerrada|ninguna",
 "entorno": "monte|bosque|agricola|periurbano|urbano",
 "cima_natural": "si|no",
 "confianza_castro": 0.0,
 "nota": "una frase corta"}

Criterios:
- recinto_cerrado: ¿se ve una plataforma llana con un borde que la envuelve
  formando un anillo cerrado? "parcial" si el borde solo cubre parte de la vuelta.
- aterrazamiento: líneas paralelas siguiendo curvas de nivel en ladera.
- parcelario_agricola: polígonos rectos con lindes rectas, como fincas.
- cima_natural: el borde coincide con la ruptura de pendiente del propio alto,
  sin plataforma artificial dentro.
- confianza_castro: 0.0 a 1.0, cuánto se parece a un recinto fortificado
  prehistórico y no a otra cosa."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "recinto_cerrado": {"type": "string", "enum": ["si", "parcial", "no"]},
        "aterrazamiento": {"type": "string", "enum": ["si", "no"]},
        "parcelario_agricola": {"type": "string", "enum": ["si", "no"]},
        "obra_moderna": {"type": "string", "enum": ["cantera", "desmonte",
                                                    "autovia", "edificacion",
                                                    "finca_cerrada", "ninguna"]},
        "entorno": {"type": "string", "enum": ["monte", "bosque", "agricola",
                                               "periurbano", "urbano"]},
        "cima_natural": {"type": "string", "enum": ["si", "no"]},
        "confianza_castro": {"type": "number"},
        "nota": {"type": "string"},
    },
    "required": ["recinto_cerrado", "aterrazamiento", "parcelario_agricola",
                 "obra_moderna", "entorno", "cima_natural", "confianza_castro",
                 "nota"],
}

CLAVES = ["recinto_cerrado", "aterrazamiento", "parcelario_agricola",
          "obra_moderna", "entorno", "cima_natural", "confianza_castro", "nota"]


def preguntar(modelo, img: Path, timeout=300):
    """Llama a Ollama con la imagen. Devuelve dict o None."""
    payload = {
        "model": modelo,
        "prompt": PROMPT,
        "images": [base64.b64encode(img.read_bytes()).decode()],
        "stream": False,
        # **Salida estructurada.** Sin esto el modelo devolvio JSON ilegible en
        # `31` de `54` fichas (2026-08-08): un `43%` de exito, y las que fallan
        # no son aleatorias sino las mas ambiguas, que son justo las que
        # interesan. Ollama admite un esquema JSON y obliga al decodificador a
        # respetarlo, asi que deja de haber respuestas a medias o envueltas en
        # prosa. Es mas barato que reintentar y no sesga la muestra.
        "format": ESQUEMA,
        # **Este script SOLO se ejecuta con la GPU libre**, y por eso no fuerza
        # `num_gpu`. Medido el 2026-08-08: con un barrido en marcha, Ollama
        # devuelve «CUDA-capable device(s) is/are busy» y falla ficha a ficha; y
        # forzado a CPU devuelve vacio tras `81 s` por imagen. La revision de
        # fichas no es urgente, asi que espera en vez de pelear: ver
        # `vision_cuando_libre.sh`.
        # **`num_gpu` alto fuerza TODAS las capas a la GPU.** Sin esto, el
        # 2026-08-08 Ollama repartio `qwen2.5vl:7b` al `41% CPU / 59% GPU` —aun
        # habiendo `3 GB` de VRAM libres— y la revision paso de `30 s` a `236 s`
        # por ficha, con la carga del nodo en `21` sobre `12` nucleos. Ollama es
        # conservador al decidir cuantas capas descarga; si el modelo cabe, hay
        # que decirselo.
        "options": {"temperature": 0.1, "num_predict": 300, "num_gpu": 99},
    }
    try:
        p = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout),
             "http://127.0.0.1:11434/api/generate",
             "-d", "@-"],
            input=json.dumps(payload), capture_output=True, text=True)
        if p.returncode != 0 or not p.stdout:
            return None
        txt = json.loads(p.stdout).get("response", "")
    except Exception:
        return None
    # el modelo suele envolver el JSON en texto o en ```
    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(txt[i:j+1])
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fichas", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--modelo", default="qwen2.5vl:7b")
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    imgs = sorted(args.fichas.rglob("*.png"))
    if args.limite:
        imgs = imgs[:args.limite]
    print(f"fichas a revisar: {len(imgs)} | modelo: {args.modelo}", flush=True)

    hechas = set()
    if args.out.exists():
        for r in csv.DictReader(open(args.out, encoding="utf-8"), delimiter="\t"):
            hechas.add(r["ficha"])
        print(f"reanudando: {len(hechas)} ya revisadas", flush=True)

    nuevo = not args.out.exists()
    fh = open(args.out, "a", newline="", encoding="utf-8")
    w = csv.writer(fh, delimiter="\t")
    if nuevo:
        w.writerow(["ficha", "bloque"] + CLAVES)

    ok = fallo = 0
    t0 = time.time()
    for i, img in enumerate(imgs, 1):
        clave = f"{img.parent.name}/{img.stem}"
        if clave in hechas:
            continue
        d = preguntar(args.modelo, img)
        if d is None:
            fallo += 1
            print(f"  {i}/{len(imgs)} {clave}: sin respuesta válida", flush=True)
            continue
        w.writerow([clave, img.parent.name] +
                   [str(d.get(k, "")).replace("\t", " ")[:120] for k in CLAVES])
        fh.flush()
        ok += 1
        dt = (time.time() - t0) / max(ok, 1)
        print(f"  {i}/{len(imgs)} {clave}: cerrado={d.get('recinto_cerrado')} "
              f"conf={d.get('confianza_castro')} ({dt:.0f} s/ficha)", flush=True)
    fh.close()
    print(f"\nrevisadas {ok} | sin respuesta {fallo}")
    print(f"escrito: {args.out}")
    print("\nMEDIDO EL 2026-08-08, Y NO FUNCIONA: contra las 8 lecturas manuales,")
    print("qwen2.5vl:3b acierta 5/8 (p=0.088, no se distingue del azar) y deja")
    print("cuatro de sus seis campos constantes; qwen2.5vl:7b varía los campos")
    print("pero acierta 2/8, POR DEBAJO del azar, y ve cantera en 23 de 30 fichas.")
    print("Entre ellos coinciden del 20% al 37%. Usar esta salida como criterio")
    print("de orden o de descarte sería inventarse una cola. Ver la wiki:")
    print("vision-local-control-2026-08-08.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
