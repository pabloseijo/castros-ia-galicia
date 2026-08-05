#!/usr/bin/env python3
"""Banco de pruebas de rendimiento para la GPU concreta que haya delante.

No sirve para «optimizar en general»: sirve para medir, en esta tarjeta y con
este modelo, cuáles de las optimizaciones habituales ayudan. En una GTX 1070 la
respuesta resultó ser que dos de las tres canónicas no valen —AMP no acelera
porque el GP104 hace FP16 a 1/64, y `channels_last` es 5,4 veces más lento
porque necesita Tensor Cores que Pascal no tiene—, así que aquí no se da nada
por sabido.

Mide, en este orden:

1. **Ocupación por tamaño de lote**: en una GPU saturada el lote es de los pocos
   parámetros que aún mueven el rendimiento, subiendo la ocupación de los SM.
2. **`cudnn.benchmark`**: deja que cuDNN pruebe algoritmos de convolución y se
   quede el mejor. Gratis si el tamaño de entrada es fijo, que es nuestro caso.
3. **`torch.compile`**: fusión de kernels y menos sobrecarga de lanzamiento. Sin
   Tensor Cores la expectativa es baja, pero es barato comprobarlo.
4. **Techo de datos**: compara el ritmo con datos sintéticos en memoria contra el
   ritmo con el cargador real. Si coinciden, el disco no es el cuello y añadir
   `--workers` es tiempo perdido.

Uso:
    python3 scripts/bench_gpu.py --vig-dir data/galicia-vignettes-v2
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_unet_multiclass import UNetMulticlass, Vignettes  # noqa: E402
from torch.utils.data import DataLoader


def cronometrar(paso, n=8, calentar=3):
    for _ in range(calentar):
        paso()
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(n):
        paso()
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) / n


def hacer_paso(model, opt, scaler, crit, x, y, amp):
    def paso():
        opt.zero_grad(set_to_none=True)
        with torch.autocast("cuda", enabled=amp):
            loss = crit(model(x)[0], y)
        scaler.scale(loss).backward()
        scaler.step(opt)
        scaler.update()
    return paso


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vig-dir", type=Path)
    ap.add_argument("--head", default="cls", choices=("cls", "mil"))
    ap.add_argument("--encoder", default="resnet34")
    ap.add_argument("--batches", type=int, nargs="+", default=[8, 16, 24, 32])
    ap.add_argument("--size", type=int, default=512)
    args = ap.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("sin GPU")
    print(f"GPU: {torch.cuda.get_device_name(0)} "
          f"| capacidad {torch.cuda.get_device_capability(0)}")
    print(f"reloj max: {torch.cuda.get_device_properties(0).max_clock_rate/1000:.0f} MHz"
          if hasattr(torch.cuda.get_device_properties(0), "max_clock_rate") else "")
    crit = nn.CrossEntropyLoss()

    def construir(bs, compilar=False, benchmark=True):
        torch.backends.cudnn.benchmark = benchmark
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        m = UNetMulticlass(3, args.encoder, args.head, pretrained=False).cuda()
        if compilar:
            m = torch.compile(m)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-4)
        sc = torch.amp.GradScaler("cuda", enabled=True)
        x = torch.randn(bs, 3, args.size, args.size, device="cuda")
        y = torch.randint(0, 3, (bs,), device="cuda")
        return m, opt, sc, x, y

    print("\n=== 1. ocupación por tamaño de lote (AMP, cudnn.benchmark) ===")
    mejor_bs, mejor_ips = None, 0.0
    for bs in args.batches:
        try:
            m, opt, sc, x, y = construir(bs)
            dt = cronometrar(hacer_paso(m, opt, sc, crit, x, y, True))
            ips = bs / dt
            pico = torch.cuda.max_memory_allocated() / 2**30
            marca = ""
            if ips > mejor_ips:
                mejor_ips, mejor_bs, marca = ips, bs, "  <-- mejor"
            print(f"  lote {bs:3d}: {dt*1000:7.0f} ms  {ips:6.1f} img/s  "
                  f"{pico:4.2f} GiB{marca}")
            del m, opt, x, y
        except RuntimeError as e:
            print(f"  lote {bs:3d}: FALLO -> {str(e)[:60]}")
            torch.cuda.empty_cache()

    bs = mejor_bs or args.batches[0]
    print(f"\n=== 2. cudnn.benchmark (lote {bs}) ===")
    for flag in (False, True):
        m, opt, sc, x, y = construir(bs, benchmark=flag)
        dt = cronometrar(hacer_paso(m, opt, sc, crit, x, y, True))
        print(f"  benchmark={int(flag)}: {dt*1000:7.0f} ms  {bs/dt:6.1f} img/s")
        del m, opt, x, y

    print(f"\n=== 3. torch.compile (lote {bs}) ===")
    for comp in (False, True):
        try:
            m, opt, sc, x, y = construir(bs, compilar=comp)
            # compilar tarda en la primera pasada: mas calentamiento
            dt = cronometrar(hacer_paso(m, opt, sc, crit, x, y, True),
                             n=8, calentar=12 if comp else 3)
            print(f"  compile={int(comp)}: {dt*1000:7.0f} ms  {bs/dt:6.1f} img/s")
            del m, opt, x, y
        except Exception as e:
            print(f"  compile={int(comp)}: FALLO -> {str(e)[:80]}")
            torch.cuda.empty_cache()

    if args.vig_dir and (args.vig_dir / "index.tsv").exists():
        print(f"\n=== 4. techo de datos: sintetico vs cargador real (lote {bs}) ===")
        rows = [r for r in csv.DictReader(
            open(args.vig_dir / "index.tsv", encoding="utf-8"), delimiter="\t")
            if (args.vig_dir / "arrays" / f"{r['sid']}.npz").exists()][:600]
        for nw in (2, 4, 6):
            m, opt, sc, x0, y0 = construir(bs)
            dl = DataLoader(Vignettes(rows, args.vig_dir / "arrays", augment=True),
                            batch_size=bs, shuffle=True, num_workers=nw,
                            pin_memory=True, persistent_workers=True)
            it = iter(dl)
            next(it)
            torch.cuda.synchronize()
            t0, n = time.perf_counter(), 0
            for xb, yb, _ in it:
                xb = xb.cuda(non_blocking=True); yb = yb.cuda(non_blocking=True)
                hacer_paso(m, opt, sc, crit, xb, yb, True)()
                n += len(yb)
                if n >= 320:
                    break
            torch.cuda.synchronize()
            real = n / (time.perf_counter() - t0)
            print(f"  workers {nw}: {real:6.1f} img/s reales "
                  f"({real/mejor_ips*100:5.1f}% del techo sintetico)")
            del m, opt, dl
        print("  Si el porcentaje ronda el 100%, el disco NO es el cuello")
        print("  y subir --workers no compra nada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
