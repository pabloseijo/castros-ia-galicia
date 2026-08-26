# Castros IA — Galicia

Detección de castros bajo vegetación a partir de LiDAR aéreo, con una U-Net sobre
modelos digitales del terreno.

**El objetivo es encontrar castros que no estén en ningún catálogo.** No sustituir
al arqueólogo: reducirle el terreno que tiene que mirar, de una provincia entera a
una lista corta.

> Repositorio **privado**. Contiene coordenadas de yacimientos no verificados —
> ver [Política de datos](#política-de-datos), que no es una formalidad.

---

## Estado, a 26 de agosto de 2026

El conjunto de prueba —el norte de Portugal, `282` castros apartados y nunca
mirados— **se abrió el 23 de agosto de 2026**. Estas son las primeras cifras del
proyecto que no están contaminadas por decisiones tomadas sobre los mismos datos.

| | |
| --- | --- |
| verdad efectiva | **`129` castros** que el barrido pudo ver |
| celdas evaluadas | `50.781`, cuatro modelos, cero truncados |
| **F1** | **`0,284`** |
| **precisión en cabecera** (VPP) | **`0,31`** |

### Contra el estado del arte, contando igual

Comparado con el trabajo publicado más cercano, sobre **la misma región** y con el
mismo criterio —contra catálogo, sin ascensos humanos—:

| | este proyecto | Canedo *et al.* (misma región) |
| --- | ---: | ---: |
| F1 | `0,284` | `0,310` |
| precisión | **`0,348`** | `0,184` |

**El `92%` del F1 de referencia, con casi el doble de precisión.**

### Lo que de verdad se aprendió al abrir el precinto

No fue el F1. Fue que al cruzar la frontera **el recall aguanta** (`0,238` frente a
`0,240` en Galicia) y **la precisión se parte por la mitad** (`0,61` → `0,31`).

El modelo ve lo mismo a los dos lados. Lo que cambia es **cuántas de sus alarmas
están ya catalogadas**.

Y al revisar `30` de esos falsos positivos uno a uno, y cruzarlos con el catálogo
oficial portugués (Endovélico), resultó que **no hay una causa, hay dos**:

| zona | candidatos con castro oficial a `<500` m | tasa base (azar) | |
| --- | ---: | ---: | --- |
| **Trás-os-Montes** (monte) | **`33%`** | `12%` | catálogo incompleto |
| **Minho** (tierra de labor) | `6%` | `9%` | confusores reales |

En el monte, el modelo encuentra cosas que el catálogo no tiene. En la tierra de
labor, se come el parcelario agrícola. Tratar «el norte de Portugal» como una
región homogénea era el error.

> Con `n = 12` en Trás-os-Montes y corrección por comparaciones múltiples, **el
> resultado es sugerente y no concluyente**. Está declarado como tal.

### Confusores dominantes, medidos sobre `30` fichas

| | |
| --- | ---: |
| parcelario agrícola y bancales | **`37%`** |
| laderas erosionadas y cárcavas | `20%` |
| infraestructura (caminos, autovías) | `13%` |

Uno de los falsos positivos era **un nudo de autopista**: los lazos del trébol son
círculos perfectos.

---

## La configuración congelada

Escrita en [`CONGELADO.md`](CONGELADO.md) el **11 de agosto de 2026**, *antes* de
mirar un solo dato portugués. Ese es todo su valor: si se pudiera reescribir
después de ver el resultado, no congelaría nada.

| pieza | valor |
| --- | --- |
| método | **fusión por rango (RRF)** de cuatro modelos |
| miembros | `v7`, `v7last`, `v8`, `v12` |
| `k` de RRF | `60` (valor estándar, no ajustado) |
| enlace | `512 m` |
| celdas retenidas | `100` por bloque |
| tolerancia de acierto | `500 m` |
| criba de falsos positivos | **ninguna** |
| diezmado de densidad | `2,0 pt/m²`, **solo en Portugal** |

---

## El protocolo de conjuntos, que es lo que sostiene las cifras

Tres conjuntos, y el tercero estuvo precintado hasta el 23 de agosto:

- **`train`** y **`validation`** — Galicia. Aquí se ajusta todo: checkpoint,
  umbral, enlace, criba.
- **`test`** — norte de Portugal, `282` castros, LiDAR abierto de la DGT.

**Un bloque nunca visto por el modelo no es conjunto de prueba si se usa para
elegir un umbral.** La configuración también es un parámetro ajustado. Pasó con
Lugo: su `F1 0,743` está inflado y así queda etiquetado.

`detection_eval.py` **se niega** a evaluar contra una verdad precintada sin
`--romper-precinto "motivo"`, y al romperlo escribe fecha y motivo en
[`data/PRECINTO-TEST.md`](data/PRECINTO-TEST.md), que es *append-only* y está en
git. Ese fichero tiene hoy **tres lecturas anotadas**, cada una con lo que
corrigió de la anterior.

---

## Estructura

```text
.
├── CONGELADO.md              la configuración, escrita antes de mirar Portugal
├── PIPELINE.md               el flujo de extremo a extremo
├── Makefile                  atajos de las tareas frecuentes
├── configs/                  parámetros de entrenamiento y barrido
├── data/                     verdades, catálogos y salidas ligeras
│   ├── PRECINTO-TEST.md      libro de cuentas del conjunto de prueba
│   └── CHECKPOINT-CONGELADO  la receta activa
├── docs/
│   ├── preregistros/         16 preregistros: qué se esperaba ANTES de medirlo
│   ├── AGENTS-nodo.md        cómo se opera el nodo de cómputo
│   └── DESCARGA-PORTUGAL.md  la vía LAZ de la DGT y sus trampas
├── ops/
│   └── cadenas/              cadenas de entrenamiento y barrido por versión
├── scripts/                  el código: descarga, entrenamiento, barrido, evaluación
├── reports/                  informes publicables, con coordenadas redondeadas
└── webmap/                   mapa estático de inspección
```

### Los preregistros

`docs/preregistros/` guarda **16 documentos escritos antes de cada experimento**,
con la hipótesis y el listón de éxito fijados de antemano. Sirven para lo mismo
que el precinto: impedir que el criterio se ajuste a lo que salió.

Ejemplo: `PREREGISTRO-v10.md` dice *«listón: F1 medio ≥ 0.542»*. Se escribió antes
de entrenar v10.

---

## Uso

```bash
# entorno
uv venv .venv-gpu && .venv-gpu/bin/pip install -e .

# barrer un territorio con la configuración congelada
scripts/barrer_galicia_congelada.sh

# evaluar contra una verdad NO precintada
.venv-gpu/bin/python scripts/detection_eval.py \
    --pred data/sweep_X.tsv --truth data/X_truth.tsv --tol 500

# fusionar varios modelos por rango
.venv-gpu/bin/python scripts/fusionar_barridos_rrf.py \
    --pred a.tsv b.tsv --names v7 v8 --out-top out.tsv --top-k 100 --rrf-k 60
```

El trabajo por lotes **no se ejecuta en un portátil**: va a un nodo con GPU. Ver
[`docs/AGENTS-nodo.md`](docs/AGENTS-nodo.md).

---

## Política de datos

Esto no es burocracia: **publicar la ubicación de un yacimiento sin verificar
puede hacer que lo expolien.**

- Las salidas de inferencia con **coordenadas precisas de celdas no revisadas**
  están en `.gitignore` y **no salen de la máquina**.
- Lo publicable es `reports/`, donde las coordenadas van **redondeadas a ~1 km**.
- Nada de lo que hay aquí ha sido verificado por un arqueólogo. Un candidato con
  puntuación alta **no es un yacimiento**: es un sitio que merece que alguien lo
  mire.
- El repositorio es privado, y esa es una decisión, no un descuido.

---

## Lo que este proyecto no afirma

- **No ha descubierto ningún castro.** Ha producido candidatos, y uno de ellos
  —un recinto ovalado de doble anillo con croa central— no aparece ni en el
  catálogo propio ni en Endovélico. Eso es una pregunta abierta, no un hallazgo.
- **Ninguna cifra es todavía una estimación insesgada de despliegue**, salvo la
  del precinto abierto, y solo esa.
- La revisión visual de candidatos la ha hecho un modelo de lenguaje, no un
  arqueólogo. Vale como cribado; no vale como dictamen. Y ya se ha medido dónde
  falla: en tres casos dio «nada» donde el catálogo oficial tiene un castro a
  menos de `450` m.

---

## Licencia y fuentes

- LiDAR de España: **PNOA**, © Instituto Geográfico Nacional, CC BY 4.0.
- LiDAR de Portugal: **DGT / Centro de Dados**, datos abiertos.
- Catálogo arqueológico portugués: **Endovélico**, Património Cultural I.P.
