#!/usr/bin/env python3
"""¿Rinde más la GPU con menos vatios? Se mide, no se opina.

La GTX 1070 de `oval-server` corre a `1202-1594 MHz` de un máximo de `1911`, con
`SW Thermal Slowdown: Active` a `90 °C` y consumiendo `103 W` de un techo de
`125 W`. **No está limitada por potencia: está limitada por calor.**

De ahí sale una hipótesis que es contraintuitiva y bien conocida: cuando una GPU
estrangula por temperatura, el reloj **oscila** —sube, se calienta, cae, se
enfría, sube—. Un techo de potencia más bajo produce un reloj **estable** y más
frío, y el rendimiento *sostenido* puede ser mayor que el del techo alto, no
menor. Es la diferencia entre correr a ráfagas y correr a ritmo.

Este script recorre varios techos de potencia y mide, en cada uno y con carga
real y sostenida: imágenes por segundo, reloj medio, temperatura de equilibrio y
si el estrangulamiento térmico llegó a activarse.

**Necesita root** para `nvidia-smi -pl`. En esta máquina `sudo -n` falla, así que
o se ejecuta como root o se añade la línea de `sudoers` que documenta
[[gpu-limitada-por-calor]]. Sin eso, el script lo dice y no finge.

Uso:
    sudo python3 scripts/bench_limite_potencia.py --vatios 125 110 100 90 80 \\
        --segundos 120
"""
from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import torch


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True)


def fijar_vatios(w):
    r = sh("nvidia-smi -pl %d" % w)
    ok = r.returncode == 0
    return ok, (r.stdout + r.stderr).strip().splitlines()[0][:90] if not ok else ""


def muestrear(parar, muestras):
    while not parar.is_set():
        r = sh("nvidia-smi --query-gpu=clocks.sm,temperature.gpu,power.draw,"
               "utilization.gpu --format=csv,noheader,nounits")
        try:
            c, t, p, u = [float(x) for x in r.stdout.strip().split(", ")]
            muestras.append((c, t, p, u))
        except Exception:
            pass
        time.sleep(2.0)


def estrangulado():
    r = sh("nvidia-smi -q -d PERFORMANCE")
    for ln in r.stdout.splitlines():
        if "SW Thermal Slowdown" in ln and "Active" in ln and "Not Active" not in ln:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vatios", type=int, nargs="+",
                    default=[125, 110, 100, 90, 80])
    ap.add_argument("--segundos", type=int, default=120,
                    help="carga sostenida por punto; corto no mide equilibrio")
    ap.add_argument("--enfriar", type=int, default=45,
                    help="pausa entre puntos para partir del mismo sitio")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--out", type=Path, default=Path("data/bench_potencia.json"))
    args = ap.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("sin CUDA: este banco no tiene sentido en CPU")

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from train_unet_multiclass import UNetMulticlass

    modelo = UNetMulticlass(3, "resnet34", "cls", pretrained=False).cuda().eval()
    x = torch.randn(args.batch, 3, 512, 512, device="cuda")
    opt = torch.optim.SGD(modelo.parameters(), lr=1e-4)

    ok, msg = fijar_vatios(args.vatios[0])
    if not ok:
        print("NO se puede fijar el techo de potencia: %s" % msg)
        print("Hace falta root. Sin eso este banco no mide nada: aborta.")
        return 2

    resultados = []
    for w in args.vatios:
        ok, msg = fijar_vatios(w)
        if not ok:
            print("  %d W: no se pudo fijar (%s)" % (w, msg))
            continue
        print("\n=== techo %d W: enfriando %d s ===" % (w, args.enfriar), flush=True)
        time.sleep(args.enfriar)

        muestras, parar = [], threading.Event()
        hilo = threading.Thread(target=muestrear, args=(parar, muestras), daemon=True)
        hilo.start()

        # Carga sostenida y realista: paso completo de entrenamiento, no solo
        # inferencia. Es lo que de verdad calienta y lo que queremos acelerar.
        torch.cuda.synchronize()
        t0, n = time.time(), 0
        while time.time() - t0 < args.segundos:
            opt.zero_grad(set_to_none=True)
            lg, _ = modelo(x)
            lg.float().pow(2).mean().backward()
            opt.step()
            n += args.batch
        torch.cuda.synchronize()
        dt = time.time() - t0
        parar.set(); hilo.join(timeout=4)

        m = np.array(muestras) if muestras else np.zeros((1, 4))
        # La segunda mitad es el equilibrio; la primera aún viene fría.
        eq = m[len(m)//2:] if len(m) > 3 else m
        r = {"vatios": w, "img_s": n/dt,
             "reloj_medio": float(eq[:, 0].mean()),
             "reloj_min": float(eq[:, 0].min()),
             "temp_equilibrio": float(eq[:, 1].mean()),
             "temp_max": float(m[:, 1].max()),
             "potencia_media": float(eq[:, 2].mean()),
             "estrangulado": estrangulado()}
        resultados.append(r)
        print("  %3d W -> %6.1f img/s | reloj %4.0f MHz (min %4.0f) | "
              "%.0f C equilibrio (%.0f max) | %.0f W | estrangula: %s"
              % (w, r["img_s"], r["reloj_medio"], r["reloj_min"],
                 r["temp_equilibrio"], r["temp_max"], r["potencia_media"],
                 "SÍ" if r["estrangulado"] else "no"), flush=True)

    fijar_vatios(max(args.vatios))
    if resultados:
        mejor = max(resultados, key=lambda r: r["img_s"])
        base = next((r for r in resultados if r["vatios"] == max(args.vatios)), None)
        print("\n=== veredicto ===")
        print("  mejor rendimiento sostenido: %d W con %.1f img/s a %.0f C"
              % (mejor["vatios"], mejor["img_s"], mejor["temp_equilibrio"]))
        if base and mejor["vatios"] < base["vatios"]:
            print("  BAJAR el techo GANA: %+.1f%% de rendimiento y %.0f C menos"
                  % (100*(mejor["img_s"]/base["img_s"]-1),
                     base["temp_equilibrio"]-mejor["temp_equilibrio"]))
        elif base:
            print("  el techo alto sigue ganando; el límite no es la potencia")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(resultados, indent=2))
        print("  escrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
