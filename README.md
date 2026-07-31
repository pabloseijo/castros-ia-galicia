# Castros IA Galicia

MVP técnico para explorar detección y priorización de castros en la comarca histórica de Trasancos mediante datos abiertos, revisión QGIS y futura preparación de rasters PNOA/LiDAR.

Repositorio privado: https://github.com/pabloseijo/castros-ia-galicia

El objetivo no es declarar nuevos yacimientos por IA. El objetivo defendible es construir un flujo reproducible para:

1. reunir castros conocidos y pistas documentadas,
2. separar fuentes fuertes, débiles, conflictivas y sin coordenadas,
3. crear capas revisables en QGIS,
4. preparar ventanas raster y etiquetas humanas,
5. evaluar si un modelo ayuda a priorizar revisión arqueológica.

## Estado actual

- Dataset maestro MVP: 125 filas.
- Puntos con coordenadas WGS84: 99.
- Buffers provisionales para revisión: 48.
- Ventanas raster candidatas: 48.
- Negativos difíciles generados para revisión: 160.
- Tareas de geocodificación: 26.
- Workspace editable de anotación: 3 capas y 2 tablas de decisiones.
- Colas de revisión: P0/P1/P2, O Val y geocodificación.
- Manifiesto de ventanas raster: 48 tiles candidatos de 512 m.
- Readiness de entrenamiento: bloqueado hasta tener polígonos/negativos revisados.
- Mapa web estático de inspección rápida.

O Val queda como holdout narrativo. No se usa para entrenar en la primera versión.

Split espacial actual:

- `train`: Ferrol, Valdoviño y Neda, 29 positivos candidatos.
- `val`: San Sadurniño, 5 positivos candidatos.
- `test`: Narón no-O-Val, 10 positivos candidatos.
- `test_o_val`: O Val, 4 positivos candidatos.

La auditoría metodológica está en `docs/literature-audit-2026-07-31.md`.

## Estructura

```text
castros-ia-galicia/
├── configs/
├── data/
│   ├── external/          # rasters/LAZ fuera de git
│   ├── processed/         # outputs ligeros reproducibles
│   ├── qgis-review/       # paquete QGIS generado para revisión
│   └── annotations/       # capas editables para revisión humana
├── docs/
├── notebooks/
├── qgis/
├── reports/
├── scripts/
└── src/
```

## Comandos

```bash
make dataset
make qgis-review
make annotations
make reports
make raster-prep
make pba-unlock
make pba-review
make training-manifest
make webmap
make env-check
make sync-wiki
make verify
```

## Política de datos

Los datos pesados PNOA/LiDAR/Sentinel no se versionan aquí. Deben vivir fuera de la wiki, por ejemplo en:

`/Users/pabloseijo/Documents/CastrosIA/data`

Las capas generadas aquí son ligeras y reproducibles. Los buffers de 120 m son semillas de revisión, no perímetros arqueológicos.

## Flujo QGIS

Abrir estos dos GeoPackage juntos:

- `data/qgis-review/castros_trasancos_qgis_review.gpkg`: capas generadas para mirar, no editar.
- `data/annotations/castros_annotations.gpkg`: capas editables para dibujar y decidir.

El siguiente paso real es revisar las tareas P0, ajustar buffers a polígonos reales en `labels_reviewed`, aceptar negativos en `negative_areas_reviewed` y solo después descargar/procesar rasters para ventanas útiles.

## Reportes operativos

- `reports/review_status.md`: cola de revisión y bloqueos.
- `reports/geocoding_blockers.md`: filas que siguen sin coordenada segura.
- `reports/raster_tile_plan.md`: ventanas raster candidatas.
- `reports/pba_catalog_unlock.md`: consulta fact-checkeada del PBA/Xunta para desbloquear geocodificación.
- `reports/remaining_geocoding_source_audit.md`: segunda pasada de fuentes para las 9 filas aún bloqueadas tras PBA.
- `reports/training_readiness.md`: estado de exportación entrenable.
- `reports/environment_status.md`: herramientas locales disponibles/bloqueantes.
- `data/review-queues/`: colas TSV por prioridad.
- `data/raster-prep/candidate_raster_tiles.tsv`: manifiesto de tiles.
- `data/training/`: manifiestos exportados desde anotaciones aceptadas.
- `webmap/index.html`: mapa estático con capas embebidas para inspección rápida.

## Mapa web

Abrir:

`webmap/index.html`

La vista web ayuda a detectar errores gruesos de coordenadas y distribución. No sustituye QGIS ni permite crear etiquetas finales.
