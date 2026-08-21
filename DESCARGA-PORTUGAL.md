# Qué bajar del portal de la DGT, exactamente

Escrito el `2026-08-11`. Actualizado el `2026-08-13`: la descarga manual por
carrito ya no es necesaria. El catálogo STAC público devuelve los assets, y una
sesión autenticada en el CDD genera URLs S3 firmadas para descargarlos de forma
reanudable.

**Portal**: `https://cdd.dgterritorio.gov.pt` — datos abiertos, licencia **CC-BY**,
registro gratuito. La descarga de ficheros requiere login, pero el catálogo STAC
está abierto en `https://dgt-be.a.incd.pt:8081`.

## 0 · Estado operativo desde el 2026-08-13

La vía vigente es:

```bash
scripts/cdd_portugal_download.py --orders 1 --collections MDT-50cm LAZ
```

Para tandas posteriores se puede subir la concurrencia sin cambiar el layout de
salida:

```bash
scripts/cdd_portugal_download.py --orders 2 --collections MDT-50cm LAZ --workers 4
```

El script:

1. Lee `data/plan-descarga-portugal.tsv`.
2. Consulta STAC por rectángulo y colección.
3. Entra al CDD con `CDD_USERNAME` / `CDD_PASSWORD` en `.env`.
4. Firma cada asset con `HEAD /dgt-be/v1/download/<hash>`.
5. Descarga desde la URL S3 firmada a `data/entrada-portugal/<orden>/<coleccion>/`.

Comprobado en el lote `1`: `78` assets `MDT-50cm` (`1,22 GB`) y `78` assets
`LAZ` (`9,12 GB`). El manifiesto completo de las `76` peticiones queda en
`data/cdd-portugal-assets-full.tsv`: `15.553` GeoTIFF `MDT-50cm` (`273,32 GB`) y
`15.554` LAZ (`2,38 TB`).

El precinto sigue intacto: esta descarga no ejecuta `detection_eval.py`.

Tras cada fusión válida, `scripts/ingerir_portugal.sh` lanza ya el cierre
autónomo de revisión:

1. `scripts/triage_morfologico.py` como bot geométrico, con `--crs EPSG:3763`.
2. `scripts/portugal_visual_ai_review.py` sobre Ollama local
   (`qwen2.5vl:7b` por defecto), generando fichas PNG, GeoJSON para QGIS y un
   TSV/JSONL de veredictos visuales.

La revisión IA **ordena y prioriza**, no valida contra verdad. Se puede ajustar
con:

```bash
PORTUGAL_AI_TOP_N=20 PORTUGAL_AI_MODEL=qwen2.5vl:7b scripts/ingerir_portugal.sh
```

Y se puede desactivar solo para depuración:

```bash
PORTUGAL_AI_REVIEW=0 scripts/ingerir_portugal.sh
```

---

## 1 · Qué producto pedir, y por qué importa

El portal ofrece tres cosas sobre la misma zona. **No dan el mismo resultado**, y
la diferencia no es de tamaño sino de qué se puede concluir después.

| producto | una petición de `200 km²` | las `76` completas | qué introduce |
| --- | ---: | ---: | --- |
| **nube LAZ** `10 pt/m²` | **`~9,12 GB` en la petición 1** | `2,38 TB` según STAC | **nada**: la tubería es la misma que en Galicia, solo cambia la geografía |
| **MDT GeoTIFF `50 cm`** | `~1,22 GB` en la petición 1 | `273,32 GB` según STAC | su clasificación de suelo y su relleno de huecos |
| MDT GeoTIFF `2 m` | `~0,2 GB` | `~15 GB` | lo anterior **más** un cambio de resolución |

El proyecto lleva la semana entera evitando exactamente este confusor: si el `F1`
cae en Portugal, **hay que poder decir si es porque el modelo no generaliza o
porque la tubería cambió**. Con la nube LAZ solo cambia una cosa; con el ráster,
tres.

## 2 · El plan: una petición de prueba, y luego decidir

Bajar `2,38 TB` de LAZ por una conexión de casa sigue siendo pesado. Y bajar solo el ráster
deja el resultado ambiguo. Así que:

> **Primera petición: la número `1` del plan, en LOS DOS formatos.**
>
> Son `~10,34 GB` una sola vez, cubre **`12` castros**, y sirve para medir si el
> ráster de `50 cm` da lo mismo que la nube. Si coinciden, las `75` restantes se
> bajan como ráster (`273,32 GB` en total según STAC). Si no
> coinciden, ya sabemos que el ráster no vale y se decide con ese dato en la
> mano.

Es la misma lógica que desbloqueó `--dem-dir` el `2026-08-11`: **medir las dos
vías contra la misma referencia antes de fiarse de ninguna.**

## 3 · Los rectángulos, en orden

Están en `data/plan-descarga-portugal.tsv`, ordenados **por castros aportados**,
no por geografía. Las primeras filas:

| orden | castros | acumulado | rectángulo (lon/lat WGS84) |
| ---: | ---: | ---: | --- |
| `1` | `12` | `4%` | `-7.1835, 41.9404` → `-7.0135, 42.0683` |
| `2` | `11` | `8%` | `-8.5436, 41.4286` → `-8.3736, 41.5566` |

Y los hitos:

| cobertura del precinto | peticiones | superficie |
| --- | ---: | ---: |
| **`50%` de los `282` castros** | **`18`** | `3.600 km²` |
| `80%` | `40` | `8.000 km²` |
| `100%` | `76` | `15.200 km²` |

**Con `18` peticiones ya hay medio conjunto de prueba**, y medio conjunto medido
es infinitamente más que ninguno.

## 4 · Dónde dejar los ficheros

```text
seijo@oval-server:~/castros/data/entrada-portugal/<orden>/
```

Un directorio por petición, con su número. El orquestador los recoge solo: los
convierte, los barre, evalúa y **borra el original**, de modo que el disco nunca
tiene más de una petición a la vez. Es reanudable: si se corta, no rehace lo ya
barrido.

El descargador deja subcarpetas por colección:

```text
data/entrada-portugal/1/MDT-50cm/*.tif
data/entrada-portugal/1/LAZ/*.laz
```

`scripts/ingerir_portugal.sh` busca LAZ recursivamente y barre Portugal en
`EPSG:3763`; no hay que mover los ficheros a mano.

La configuración congelada no es un checkpoint único. El ingestor ejecuta los
cuatro barridos:

```text
v7      -> data/cls-v7/best.pt
v7last  -> data/cls-v7/last.pt
v8      -> data/cls-v8/best.pt
v12     -> data/cls-v12/best.pt
```

Después fusiona con RRF (`k=60`) y deja:

```text
data/sweep_test_portugal_<orden>_fusion_rrf_full.tsv
data/sweep_test_portugal_<orden>.tsv       # top 100 celdas congeladas
```

Para el lote piloto se puede conservar el original:

```bash
PORTUGAL_KEEP_INPUT=1 scripts/ingerir_portugal.sh
```

## 5 · Lo que hay que comprobar al bajar la primera

1. **Que el noroeste está publicado.** La propia DGT decía que el `~90%` del
   territorio estaba listo y **el noroeste seguía en producción**. Si el visor no
   deja seleccionar la zona, ese es el bloqueo real y no hay ingeniería que lo
   arregle.
2. **El CRS de los ficheros**: debería ser `ETRS89 / PT-TM06`, **EPSG:3763**.
   Nuestra tubería trabaja en `EPSG:25829` (ETRS89 / UTM 29N), así que hay
   reproyección, y está contemplada.

## 6 · Lo que NO hay que hacer

- **No mirar ninguna predicción sobre estos datos** hasta que el modelo esté
  congelado por escrito (fase 2 del roadmap). El precinto se abre una vez.
- **No bajar solo las zonas con castros sin fondo alrededor.** El plan ya
  incluye margen: sin negativos, la precisión medida no significa nada, que es
  exactamente el error de la confusión espacial de v14.
