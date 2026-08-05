#!/usr/bin/env python3
"""Monta hojas de contacto: ortofoto | sombreado | relieve local, una fila por candidato.

Existe para que la revisión visual sea **mirable de una vez** en lugar de setenta y
cinco imágenes sueltas. Cada fila enseña el mismo recorte de `512 m` en las tres
capas que un arqueólogo abre en QGIS a la vez, y esa comparación es el gesto que
descarta: si en relieve hay un anillo perfecto y en ortofoto hay una cantera, no
hace falta discutirlo.

Uso:
    python3 scripts/build_review_contact_sheets.py --orto data/revision-visual-v1/orto \\
        --relieve data/revision-visual-v1/relieve --out data/revision-visual-v1/hojas \\
        --por-hoja 5
"""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

import numpy as np


def leer_png(path):
    """Decodifica PNG de 8 bits, gris o RGB(A). Solo lo que generamos y el IGN sirve."""
    datos = Path(path).read_bytes()
    assert datos[:8] == b"\x89PNG\r\n\x1a\n", "no es PNG: %s" % path
    i = 8
    idat = b""
    w = h = prof = tipo = None
    while i < len(datos):
        ln = struct.unpack(">I", datos[i:i+4])[0]
        ct = datos[i+4:i+8]
        cuerpo = datos[i+8:i+8+ln]
        if ct == b"IHDR":
            w, h, prof, tipo = struct.unpack(">IIBB", cuerpo[:10])
        elif ct == b"IDAT":
            idat += cuerpo
        elif ct == b"IEND":
            break
        i += 12 + ln
    canales = {0: 1, 2: 3, 4: 2, 6: 4}[tipo]
    assert prof == 8, "solo 8 bits (%s tiene %d)" % (path, prof)
    crudo = zlib.decompress(idat)
    paso = w * canales
    salida = np.zeros((h, paso), np.uint8)
    prev = np.zeros(paso, np.int32)
    p = 0
    for y in range(h):
        filtro = crudo[p]; p += 1
        linea = np.frombuffer(crudo[p:p+paso], np.uint8).astype(np.int32); p += paso
        if filtro == 0:
            rec = linea
        elif filtro == 1:
            rec = linea.copy()
            for x in range(canales, paso):
                rec[x] = (rec[x] + rec[x-canales]) & 255
        elif filtro == 2:
            rec = (linea + prev) & 255
        elif filtro == 3:
            rec = linea.copy()
            for x in range(paso):
                izq = rec[x-canales] if x >= canales else 0
                rec[x] = (rec[x] + ((izq + prev[x]) >> 1)) & 255
        else:                                              # Paeth
            rec = linea.copy()
            for x in range(paso):
                a = rec[x-canales] if x >= canales else 0
                b = prev[x]
                c = prev[x-canales] if x >= canales else 0
                q = a + b - c
                pa, pb, pc = abs(q-a), abs(q-b), abs(q-c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                rec[x] = (rec[x] + pr) & 255
        salida[y] = rec
        prev = rec
    img = salida.reshape(h, w, canales)
    if canales == 1:
        return np.repeat(img, 3, axis=2)
    return img[:, :, :3]


def escribir_png_rgb(arr, destino):
    h, w, _ = arr.shape
    crudo = b"".join(b"\x00" + arr[y].tobytes() for y in range(h))

    def trozo(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c))

    Path(destino).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(crudo, 6))
        + trozo(b"IEND", b""))


def reescalar(img, lado):
    h, w, c = img.shape
    yi = (np.arange(lado) * h // lado).clip(0, h-1)
    xi = (np.arange(lado) * w // lado).clip(0, w-1)
    return img[yi][:, xi]


# Tipografía mínima de 5x7 para rotular sin dependencias externas.
GLIFOS = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "#": ["01010", "11111", "01010", "01010", "11111", "01010", "00000"],
    " ": ["00000"]*7,
}


def rotular(lienzo, x, y, texto, escala=3):
    for ch in texto:
        g = GLIFOS.get(ch, GLIFOS[" "])
        for fy, fila in enumerate(g):
            for fx, bit in enumerate(fila):
                if bit == "1":
                    lienzo[y+fy*escala:y+(fy+1)*escala,
                           x+fx*escala:x+(fx+1)*escala] = 255
        x += 6 * escala


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orto", type=Path, required=True)
    ap.add_argument("--relieve", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lado", type=int, default=380)
    ap.add_argument("--por-hoja", type=int, default=5)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    ids = sorted(int(p.stem.split("-")[1]) for p in args.orto.glob("cand-*.png"))
    L, SEP, BANDA = args.lado, 6, 34
    ancho = 3*L + 4*SEP

    hoja = None
    for k, cid in enumerate(ids):
        j = k % args.por_hoja
        if j == 0:
            filas = min(args.por_hoja, len(ids)-k)
            hoja = np.zeros((filas*(L+BANDA+SEP)+SEP, ancho, 3), np.uint8)
        capas = []
        for p in (args.orto / ("cand-%02d.png" % cid),
                  args.relieve / ("cand-%02d-sombra.png" % cid),
                  args.relieve / ("cand-%02d-lrm.png" % cid)):
            capas.append(reescalar(leer_png(p), L) if p.exists()
                         else np.zeros((L, L, 3), np.uint8))
        y0 = SEP + j*(L+BANDA+SEP)
        rotular(hoja, SEP, y0 + 8, "#%02d" % cid, escala=3)
        for c, cap in enumerate(capas):
            x0 = SEP + c*(L+SEP)
            hoja[y0+BANDA:y0+BANDA+L, x0:x0+L] = cap
        if j == args.por_hoja-1 or k == len(ids)-1:
            destino = args.out / ("hoja-%d.png" % (k // args.por_hoja + 1))
            escribir_png_rgb(hoja, destino)
            print("escrita %s" % destino)
    print("columnas: ortofoto PNOA | sombreado multidireccional | relieve local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
