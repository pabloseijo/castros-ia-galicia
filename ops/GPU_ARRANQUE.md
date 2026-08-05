# Arranque de la GPU — `oval-server`

> Cómo dejar `oval-server` en condiciones de entrenar, y las tres cosas que
> costaron tiempo la primera vez. Escrito el `2026-08-04` con todo medido en la
> máquina, no copiado de la documentación de nadie.

## Qué hay

| pieza | valor |
|---|---|
| GPU | GeForce GTX 1070, `8 GB` VRAM, capacidad de cómputo **`6.1` (Pascal)** |
| driver | `580.173.02` (expone CUDA `13.0`) |
| SO | Ubuntu `26.04 LTS`, kernel `7.0`, Python del sistema `3.14.4` |
| CPU / RAM | i7-8750H, `12` hilos / **`8 GB`** — la RAM es el límite real |
| disco | `914 GB`, `853 GB` libres |

## Entorno

Se usa **`uv` con Python `3.12` propio**, no el Python del sistema:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
cd ~/castros && uv venv --python 3.12 .venv-gpu
UV_HTTP_TIMEOUT=600 uv pip install --python .venv-gpu/bin/python \
  --index-url https://download.pytorch.org/whl/cu126 torch torchvision
```

Tres razones, y ninguna es que `3.14` no esté soportado —sí lo está, hay `7`
wheels `cp314` en el índice `cu126`—:

1. `python3 -m venv` del sistema **no arranca**: le falta `ensurepip`, y
   arreglarlo pide `sudo`. `uv` trae su propio Python y no toca el sistema.
2. `cp312` tiene `12` wheels en `cu126` frente a `7` de `cp314`. Más margen
   para bajar de versión si algo se rompe.
3. `UV_HTTP_TIMEOUT=600` es **obligatorio**: el wheel de `nvidia-cudnn-cu12`
   pasa de `700 MB` y con el timeout por defecto la instalación se cae a medias.

## Pascal: por qué funciona aunque el `arch_list` no lo liste

Es la trampa de esta máquina y conviene entenderla antes de perseguir un
fantasma. `torch 2.13.0+cu126` declara:

```text
arch_list = ['sm_50', 'sm_60', 'sm_70', 'sm_75', 'sm_80', 'sm_86', 'sm_90']
```

La GTX 1070 es **`sm_61`**, que **no aparece en la lista**. Y aun así funciona.
La razón es que CUDA garantiza compatibilidad binaria *hacia arriba dentro de la
misma generación mayor*: un cubin compilado para `sm_60` corre en un dispositivo
`6.x` con `x >= 0`. Lo que no existe es compatibilidad hacia atrás ni entre
generaciones mayores.

**No dar esto por bueno de memoria: comprobarlo ejecutando.**

```bash
.venv-gpu/bin/python -c "
import torch, torch.nn as nn
print(torch.__version__, torch.version.cuda, torch.cuda.get_arch_list())
print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))
a = torch.randn(2048, 2048, device='cuda'); (a @ a).sum().item()
nn.Conv2d(3, 32, 3, padding=1).cuda()(torch.randn(4, 3, 256, 256, device='cuda'))
print('GPU operativa')"
```

Cautela para el futuro: las compilaciones **`cu128` y posteriores retiraron
Maxwell, Pascal y Volta**. Si algún día `cu126` deja de publicar wheels, esta
GPU se queda sin ruta de actualización. Fijar el índice a `cu126` y no
«actualizar por actualizar».

## Rendimiento medido, para dimensionar antes de lanzar

U-Net con codificador `resnet34` sobre viñetas de `512x512x3`, AMP activado:

| cabeza | lote | VRAM pico | ms/lote | img/s |
|---|---:|---:|---:|---:|
| `mil` | `8` | `2.19 GiB` | `328` | `24.4` |
| `mil` | `12` | `3.12 GiB` | `455` | `26.4` |
| **`mil`** | **`16`** | **`4.04 GiB`** | **`583`** | **`27.4`** |
| `cls` | `8` | `1.05 GiB` | `210` | `38.1` |
| `cls` | `16` | `1.75 GiB` | `355` | `45.1` |

**Lote `16` es el punto razonable**: de `8` a `16` el rendimiento solo sube un
`12%` y la VRAM se dobla, así que subir más no compensa. Con `6.994` viñetas de
entrenamiento salen unos `350 s` por época, o `~4 h` las `40`.

## Traer el corpus desde la Raspberry

El corpus (`data/galicia-vignettes-v2/`, `8.743` ficheros, `9.07 GB`) vive en el
disco externo de la Pi. La arquitectura es **en estrella**: el orquestador manda,
los nodos no se hablan. Pero el enlace del Mac es WiFi y mide **`1.9 MB/s`**, así
que relevar por el Mac son `70` minutos frente a `15`.

Excepción autorizada por Pablo el `2026-08-04`: la copia va **Pi → oval directa**,
lanzada por el orquestador. Se hizo a `9.6 MB/s`. Para no dejar la clave privada
en un segundo nodo se usa **reenvío de agente**:

```bash
ssh-add ~/.ssh/raspberri_keltera            # en el Mac
ssh -A seijo@oval-server "rsync -a --partial \
  admin@192.168.1.143:/srv/data/castros-ia-galicia-current/data/galicia-vignettes-v2/ \
  ~/castros/data/galicia-vignettes-v2/"
```

El agente vive en el Mac, así que **la sesión SSH tiene que seguir abierta**
mientras dure la copia; con `nohup` y desconexión, el socket del agente muere.

Verificar siempre al terminar, que es barato:

```bash
find . -type f | wc -l ; du -sb . | cut -f1 ; md5sum index.tsv meta.json
```

Deben salir `8.743` ficheros y `9.074.217.663` bytes en los dos lados.

## Lanzar el entrenamiento

```bash
cd ~/castros && mkdir -p logs
nohup setsid .venv-gpu/bin/python scripts/train_unet_multiclass.py \
  --vig-dir data/galicia-vignettes-v2 \
  --out-dir data/unet-multiclass-v1 \
  --head mil --encoder resnet34 \
  --epochs 40 --batch 16 --workers 6 --resume \
  > logs/unet-mil-v1.log 2>&1 < /dev/null &
```

`setsid` y `< /dev/null` no son adorno: sin ellos el proceso muere al cerrar la
sesión SSH. Y `--resume` reanuda desde `last.pt`, porque un entrenamiento de
`4 h` que solo escribe al final es un entrenamiento que no existe.

## Lo que hay que mirar mientras corre

```bash
tail -f ~/castros/logs/unet-mil-v1.log
nvidia-smi --query-gpu=utilization.gpu,memory.used,temperature.gpu --format=csv
```

- **`COLAPSADA`** en el log es la señal importante. Marca una clase con recall
  `0`, que es como fracasó Gomes et al. (`2024`) sin que su `94%` de precisión
  lo delatara. Si la mámoa sigue colapsada al final, hay que volver a binario.
- La cifra a batir es la línea base de CPU: **castro `0.722`, mámoa `0.361`**,
  fondo `0.901`. Sale impresa al final del entrenamiento.
- Temperatura: se estabiliza sobre `76 °C` al `100%` de uso. Es un portátil con
  la tapa cerrada; si sube mucho más, revisar ventilación antes que el modelo.

## Si hace falta RAM

`8 GB` es el límite real de la máquina. Durante un entrenamiento pesado:

```bash
docker stop open-webui netdata     # y volver a arrancarlos al terminar
```

No hizo falta en la primera pasada: con `6` cargadores quedaban `6 GB` libres.

## Páginas relacionadas

- `wiki/vida/infraestructura/servidor-oval-gpu.md` — la máquina y su topología.
- `wiki/vida/carrera/arqueologia-computacional/arquitectura-red-castros.md` —
  por qué U-Net y no transformer.
- `wiki/vida/infraestructura/servidor-raspberry.md` — el otro nodo, y el disco
  externo que hay que blindar antes de cualquier carga larga.
