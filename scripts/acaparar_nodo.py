#!/usr/bin/env python3
"""Toma el nodo entero para un trabajo pesado, y lo devuelve al terminar.

Regla fijada por Pablo el `2026-08-06`: **cuando hay entrenamiento o barrido, el
nodo es suyo al 100%**. Nada de compartir la GPU con Ollama ni los núcleos con
seis contenedores. Pero apagar servicios a mano es cómo se pierden: alguien los
para «un momento» y nadie recuerda cuáles estaban vivos.

Por eso esto no es un `docker stop`: es un **libro de cuentas**. `tomar` anota
qué estaba corriendo antes de tocarlo, en un JSON con fecha, y `soltar` restaura
exactamente eso y nada más. Si el trabajo revienta a las cuatro de la mañana, el
libro sigue ahí y el nodo se recupera con un comando.

## Lo que nunca se toca, y por qué

- **`sshd`, `tailscaled`, `docker.service`, `containerd`, `systemd`, red**:
  apagarlos deja el nodo inalcanzable y el trabajo sin quien lo rescate.
- **`nvidia-persistenced`**: sin él la GPU reinicializa entre procesos.
- **El propio proceso y su árbol de SSH.** Este proyecto ya se mató su propia
  sesión dos veces con `pkill -f`, porque la línea de comandos de `bash -c`
  contiene el patrón que se busca. Aquí se mata por PID y **verificando
  `/proc/PID/cmdline`** antes de disparar.

## Lo que exige decir su nombre

`vaultwarden` en `oval-server` y `AdGuardHome` en `raspberri` **no se paran por
defecto**, aunque la regla diga «todo». El primero es el gestor de contraseñas:
si se cae mientras Pablo está fuera de casa, se queda sin poder entrar a ningún
sitio. El segundo es el DNS de la casa entera: apagarlo deja sin navegar a todo
el que viva allí, y el fallo no se parece a «falta el DNS», se parece a «internet
no va». Van en `--incluso-criticos`, que hay que escribir a conciencia.

Uso:
    python3 scripts/acaparar_nodo.py tomar --motivo "entrenamiento v5"
    python3 scripts/acaparar_nodo.py estado
    python3 scripts/acaparar_nodo.py soltar
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

LIBRO = Path.home() / ".acaparar_nodo.json"
REGISTRO = Path.home() / "castros" / "logs" / "acaparar.log"

# Tocar cualquiera de estos deja el nodo inalcanzable o la GPU inservible.
INTOCABLES_SYSTEMD = {
    "sshd.service", "ssh.service", "tailscaled.service", "docker.service",
    "containerd.service", "systemd-networkd.service", "systemd-resolved.service",
    "systemd-journald.service", "systemd-logind.service", "dbus.service",
    "cron.service", "chrony.service", "nvidia-persistenced.service",
    "wpa_supplicant.service", "polkit.service", "udisks2.service",
    "networking.service", "NetworkManager.service",
}
# Se paran solo si se escribe --incluso-criticos. Ver la nota de arriba.
CRITICOS_DOCKER = {"vaultwarden", "adguardhome", "adguard"}
# Servicios propios que sí ceden el nodo. Ollama es el que de verdad importa:
# `qwen3:8b` ocupa 6 de los 8 GB de VRAM y una sola petición mata el trabajo.
SYSTEMD_CEDEN = {"ollama.service"}


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def anotar(txt):
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRO, "a", encoding="utf-8") as fh:
        fh.write("[%s] %s\n" % (dt.datetime.now().isoformat(timespec="seconds"), txt))
    print(txt, flush=True)


def contenedores_vivos():
    r = sh("docker ps --format '{{.Names}}'")
    return [n for n in r.stdout.split() if n]


def systemd_vivos():
    r = sh("systemctl list-units --type=service --state=running "
           "--no-pager --no-legend")
    vivos = set()
    for ln in r.stdout.splitlines():
        u = ln.split()[0] if ln.split() else ""
        if u in SYSTEMD_CEDEN:
            vivos.add(u)
    return sorted(vivos)


def timers_vivos():
    r = sh("systemctl list-timers --no-pager --no-legend")
    fuera = []
    for ln in r.stdout.splitlines():
        for tok in ln.split():
            if tok.endswith(".timer") and not tok.startswith("systemd"):
                fuera.append(tok)
    return sorted(set(fuera))


def procesos_gpu(mi_pid, proteger_pids=(), proteger_patrones=()):
    """PIDs con memoria en la GPU que no somos nosotros ni nuestro árbol.

    `proteger_*` existe por un fallo que esta herramienta tuvo en su primer uso:
    al tomar el nodo **para un trabajo que ya estaba corriendo**, ese trabajo se
    lanzó con `setsid` y por tanto no cuelga del árbol de la sesión SSH. La
    herramienta lo listó como ajeno, y `--matar-gpu` habría matado exactamente lo
    que venía a proteger. Quien toma el nodo tiene que poder decir qué sobrevive.
    """
    if not shutil.which("nvidia-smi"):
        return []
    r = sh("nvidia-smi --query-compute-apps=pid --format=csv,noheader")
    fuera = []
    mios = {mi_pid}
    p = mi_pid
    for _ in range(8):                      # subir por el árbol hasta init
        try:
            ppid = int(Path("/proc/%d/stat" % p).read_text().split()[3])
        except Exception:
            break
        if ppid <= 1:
            break
        mios.add(ppid)
        p = ppid
    for ln in r.stdout.split():
        try:
            pid = int(ln)
        except ValueError:
            continue
        if pid in mios or pid in set(proteger_pids):
            continue
        try:
            cmd = Path("/proc/%d/cmdline" % pid).read_bytes().decode(errors="replace")
        except Exception:
            # PID con VRAM pero sin `/proc`. **No es un contexto filtrado del
            # driver**, aunque lo parezca: es un padre muerto cuyos obreros
            # siguen vivos y mantienen su contexto CUDA abierto. Pasó el
            # 2026-08-06 con 1,2 GB de los 8, y se liberaron solos al matar a los
            # dos obreros huérfanos. Buscarlos por su línea de comandos.
            fuera.append({"pid": pid, "cmdline": "<sin /proc: padre muerto con "
                                                 "obreros vivos reteniendo su "
                                                 "contexto CUDA>"})
            continue
        cmd = cmd.replace("\x00", " ")
        if any(pat and pat in cmd for pat in proteger_patrones):
            continue
        fuera.append({"pid": pid, "cmdline": cmd[:120]})
    return fuera


def cmd_tomar(args):
    previo = {}
    if LIBRO.exists():
        if not args.forzar:
            raise SystemExit("ya hay un libro abierto en %s; usa `soltar` o "
                             "--forzar" % LIBRO)
        # `--forzar` **fusiona**, no sobrescribe. La primera versión sobrescribía,
        # y en su primer uso real eso borró la lista de seis contenedores ya
        # parados: `soltar` los habría dejado caídos para siempre, sin que nadie
        # supiera que existieron. Un libro de cuentas que olvida no sirve.
        previo = json.loads(LIBRO.read_text())
    mi_pid = os.getpid()
    libro = {"abierto": dt.datetime.now().isoformat(timespec="seconds"),
             "motivo": args.motivo, "nodo": os.uname().nodename,
             "incluso_criticos": bool(args.incluso_criticos),
             "docker": [], "systemd": [], "timers": [], "gpu_matados": [],
             "protegidos": []}

    anotar("=== TOMANDO EL NODO: %s ===" % args.motivo)

    cont = contenedores_vivos()
    for c in cont:
        if c.lower() in CRITICOS_DOCKER and not args.incluso_criticos:
            libro["protegidos"].append(c)
            anotar("  PROTEGIDO (crítico, no se para): %s" % c)
            continue
        libro["docker"].append(c)
    if libro["docker"]:
        sh("docker stop " + " ".join(libro["docker"]))
        anotar("  contenedores parados: %s" % ", ".join(libro["docker"]))

    for u in systemd_vivos():
        if u in INTOCABLES_SYSTEMD:
            continue
        r = sh("sudo -n systemctl stop %s" % u)
        if r.returncode == 0:
            libro["systemd"].append(u)
            anotar("  servicio parado: %s" % u)
        else:
            anotar("  NO se pudo parar %s (hace falta sudo con terminal): %s"
                   % (u, (r.stderr or "").strip()[:60]))

    if not args.dejar_timers:
        for t in timers_vivos():
            r = sh("sudo -n systemctl stop %s" % t)
            if r.returncode == 0:
                libro["timers"].append(t)
        if libro["timers"]:
            anotar("  temporizadores parados: %s" % ", ".join(libro["timers"]))

    # El candado de verdad. Hasta aqui «la GPU es nuestra» era una convencion:
    # se paraba lo conocido y se confiaba en que nadie mas entrase.
    # EXCLUSIVE_PROCESS lo impone el driver — un solo contexto CUDA a la vez—,
    # asi que deja de depender de que nos acordemos de parar algo.
    # Ojo: `-c 1` es Exclusive_Thread y esta obsoleto; el bueno es `-c 3`.
    # Antes de bloquear, limpiar: con EXCLUSIVE_PROCESS un contexto huerfano
    # —padre muerto cuyos obreros siguen vivos— impide arrancar cualquier
    # trabajo. Bloquear sin limpiar deja la maquina inutilizable.
    for _p in procesos_gpu(mi_pid, args.proteger_pid, args.proteger_patron):
        if "sin /proc" in _p["cmdline"]:
            anotar("  contexto huerfano en la GPU (pid %d): buscando sus hijos"
                   % _p["pid"])
            for _h in sh("pgrep -P %d" % _p["pid"]).stdout.split():
                try:
                    os.kill(int(_h), signal.SIGKILL)
                    anotar("    hijo %s eliminado" % _h)
                except Exception:
                    pass
    modo = sh("nvidia-smi -q | grep -i 'compute mode'")
    libro["compute_mode_previo"] = (modo.stdout.split(":")[-1].strip()
                                    if modo.returncode == 0 else "")
    r = sh("sudo -n /usr/bin/nvidia-smi -c 3")
    if r.returncode == 0 and "EXCLUSIVE_PROCESS" in (r.stdout + r.stderr).upper():
        anotar("  GPU en EXCLUSIVE_PROCESS: el driver bloquea a cualquier otro")
    else:
        anotar("  NO se pudo poner el candado de la GPU: %s"
               % (r.stderr or r.stdout or "").strip()[:70])
    sh("sudo -n /usr/bin/nvidia-smi -pm 1")

    # La GPU, al final: lo anterior es lo que suele tener algo cargado.
    time.sleep(3)
    for p in procesos_gpu(mi_pid, args.proteger_pid, args.proteger_patron):
        anotar("  proceso en GPU ajeno: pid %d — %s" % (p["pid"], p["cmdline"]))
        if args.matar_gpu:
            try:
                os.kill(p["pid"], signal.SIGTERM)
                libro["gpu_matados"].append(p)
                anotar("    -> SIGTERM enviado")
            except Exception as e:
                anotar("    -> no se pudo: %s" % e)
        else:
            anotar("    -> NO se mata (usa --matar-gpu si debe morir)")

    for k in ("docker", "systemd", "timers", "protegidos"):
        vistos, fusion = set(), []
        for x in previo.get(k, []) + libro[k]:
            if x not in vistos:
                vistos.add(x)
                fusion.append(x)
        libro[k] = fusion
    libro["gpu_matados"] = previo.get("gpu_matados", []) + libro["gpu_matados"]
    if previo:
        libro["abierto"] = previo.get("abierto", libro["abierto"])
        anotar("  fusionado con el libro anterior (%s)" % previo.get("motivo", "?"))
    LIBRO.write_text(json.dumps(libro, indent=2, ensure_ascii=False))
    r = sh("nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu "
           "--format=csv,noheader")
    anotar("  GPU tras tomar: %s" % r.stdout.strip())
    anotar("  libro escrito en %s" % LIBRO)
    return 0


def cmd_soltar(args):
    if not LIBRO.exists():
        raise SystemExit("no hay libro abierto: nada que restaurar")
    libro = json.loads(LIBRO.read_text())
    anotar("=== SOLTANDO EL NODO (tomado el %s para: %s) ==="
           % (libro["abierto"], libro["motivo"]))

    for u in libro.get("systemd", []):
        r = sh("sudo -n systemctl start %s" % u)
        anotar("  servicio %s: %s" % (u, "arrancado" if r.returncode == 0
                                      else "FALLÓ, arráncalo a mano"))
    for t in libro.get("timers", []):
        sh("sudo -n systemctl start %s" % t)
    if libro.get("timers"):
        anotar("  temporizadores restaurados: %s" % ", ".join(libro["timers"]))
    if libro.get("docker"):
        r = sh("docker start " + " ".join(libro["docker"]))
        anotar("  contenedores arrancados: %s" % ", ".join(libro["docker"]))
        if r.returncode != 0:
            anotar("  aviso: %s" % (r.stderr or "").strip()[:120])
    prev = libro.get("compute_mode_previo", "")
    if prev and "EXCLUSIVE" not in prev.upper():
        r = sh("sudo -n /usr/bin/nvidia-smi -c 0")
        anotar("  GPU devuelta a modo %s: %s"
               % (prev, "ok" if r.returncode == 0 else "FALLO, hazlo a mano"))
    if libro.get("gpu_matados"):
        anotar("  NO se restauran solos (se mataron por PID): %s"
               % ", ".join(p["cmdline"][:40] for p in libro["gpu_matados"]))

    hist = LIBRO.with_suffix(".json.hist")
    with open(hist, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(libro, ensure_ascii=False) + "\n")
    LIBRO.unlink()
    anotar("  libro cerrado y archivado en %s" % hist)
    return 0


def cmd_estado(args):
    if LIBRO.exists():
        libro = json.loads(LIBRO.read_text())
        print("NODO TOMADO desde %s — %s" % (libro["abierto"], libro["motivo"]))
        for k in ("docker", "systemd", "timers", "protegidos"):
            if libro.get(k):
                print("  %-12s %s" % (k + ":", ", ".join(
                    x if isinstance(x, str) else str(x) for x in libro[k])))
    else:
        print("nodo libre: no hay libro abierto")
    print("\ncontenedores vivos ahora: %s" % (", ".join(contenedores_vivos()) or "ninguno"))
    r = sh("nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,"
           "clocks.sm,temperature.gpu --format=csv,noheader")
    if r.returncode == 0:
        print("GPU: %s" % r.stdout.strip())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tomar", help="parar todo y anotar qué estaba vivo")
    t.add_argument("--motivo", required=True)
    t.add_argument("--incluso-criticos", action="store_true",
                   help="para también vaultwarden y AdGuardHome; lee la nota")
    t.add_argument("--dejar-timers", action="store_true")
    t.add_argument("--matar-gpu", action="store_true",
                   help="SIGTERM a procesos ajenos con memoria en la GPU")
    t.add_argument("--proteger-pid", type=int, nargs="*", default=[],
                   help="PIDs que sobreviven aunque tengan memoria en la GPU")
    t.add_argument("--proteger-patron", nargs="*", default=[],
                   help="subcadenas de cmdline que sobreviven; para trabajos "
                        "ya lanzados con setsid, que no cuelgan de esta sesión")
    t.add_argument("--forzar", action="store_true")
    t.set_defaults(func=cmd_tomar)

    s = sub.add_parser("soltar", help="restaurar exactamente lo anotado")
    s.set_defaults(func=cmd_soltar)

    e = sub.add_parser("estado", help="qué está tomado y cómo va la GPU")
    e.set_defaults(func=cmd_estado)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
