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
make viladonga-audit
make viladonga-wcs-dem
make viladonga-relief-wcs
make viladonga-lidar-derivatives
make viladonga-pnoa-chips
make viladonga-pilot
make pba-unlock
make pba-review
make training-manifest
make webmap
make env-check
make annotation-backup
make repo-drift
make sync-wiki
make agent-list
make agent-run
make verify
```

## Política de datos

Los datos pesados PNOA/LiDAR/Sentinel no se versionan aquí. Deben vivir fuera de la wiki, por ejemplo en:

`/Users/pabloseijo/Documents/CastrosIA/data`

Las capas generadas aquí son ligeras y reproducibles. Los buffers de 120 m son semillas de revisión, no perímetros arqueológicos.

## Piloto morfológico Viladonga

La ruta de arranque para detectar forma no depende de Trasancos. Usa el piloto original del TFG en Viladonga:

```bash
make viladonga-audit
make viladonga-relief-wcs
make viladonga-lidar-derivatives
make viladonga-pnoa-chips
```

Documentación: `docs/viladonga-morphology-pilot.md`.

La finalidad es probar chips, máscaras y derivados de relieve sobre un castro conocido. No es un dataset suficiente para entrenar un modelo serio.

## Flujo QGIS

Abrir estos dos GeoPackage juntos:

- `data/qgis-review/castros_trasancos_qgis_review.gpkg`: capas generadas para mirar, no editar.
- `data/annotations/castros_annotations.gpkg`: capas editables para dibujar y decidir.

El siguiente paso real es revisar las tareas P0, ajustar buffers a polígonos reales en `labels_reviewed`, aceptar negativos en `negative_areas_reviewed` y solo después descargar/procesar rasters para ventanas útiles.

`make annotations` conserva el GeoPackage editable si ya existe. Para recrearlo desde cero hay que usar `make annotations-reset`, solo después de respaldar cualquier edición humana.

## Reportes operativos

- `reports/review_status.md`: cola de revisión y bloqueos.
- `reports/geocoding_blockers.md`: filas que siguen sin coordenada segura.
- `reports/raster_tile_plan.md`: ventanas raster candidatas.
- `reports/pba_catalog_unlock.md`: consulta fact-checkeada del PBA/Xunta para desbloquear geocodificación.
- `reports/remaining_geocoding_source_audit.md`: segunda pasada de fuentes para las 9 filas aún bloqueadas tras PBA.
- `data/qgis-review/remaining_equivalence_candidates.geojson`: capa visual con las dos equivalencias posibles que requieren decisión humana.
- `reports/training_readiness.md`: estado de exportación entrenable.
- `reports/environment_status.md`: herramientas locales disponibles/bloqueantes.
- `reports/environment_status_raspberry.md`: herramientas disponibles en la Raspberry para agentes remotos.
- `reports/annotation_backup_status.md`: estado del backup/verificación del GeoPackage editable.
- `reports/repo_drift_status.md`: estado Git local/remoto sin auto-merge.
- `reports/pnoa_preview_index.md`: estado del índice de previsualización PNOA.
- `reports/pnoa_chip_export.md`: estado de exportación de chips PNOA desde anotaciones aceptadas.
- `reports/viladonga_pilot_readiness.md`: auditoría del piloto morfológico de Viladonga.
- `reports/viladonga_mdt_wcs.md`: recorte MDT5 por WCS para desbloquear relieve grueso.
- `reports/viladonga_lidar_derivatives.md`: derivados LiDAR/relieve generados para Viladonga.
- `reports/viladonga_laz_tile_blocker.md`: teselas LAZ correctas que faltan para relieve LiDAR fino.
- `reports/viladonga_pnoa_chips.md`: chips PNOA y máscaras de segmentación para Viladonga.
- `data/review-queues/`: colas TSV por prioridad.
- `data/raster-prep/candidate_raster_tiles.tsv`: manifiesto de tiles.
- `data/raster-prep/pnoa_preview_urls.tsv`: enlaces WMS PNOA de solo revisión para cada ventana candidata.
- `data/training/`: manifiestos exportados desde anotaciones aceptadas.
- `data/training/pnoa_chip_manifest.tsv`: chips PNOA exportados desde etiquetas aceptadas; permanece vacío mientras no haya revisión QGIS aceptada.
- `data/viladonga-pilot/`: manifiestos ligeros del piloto controlado.
- `webmap/index.html`: mapa estático con capas embebidas para inspección rápida.
- `webmap/pnoa_preview_index.html`: tabla HTML con miniaturas WMS PNOA para revisión visual; no crea etiquetas.
- `docs/raspberry-agents.md`: runner agentico para Raspberry con systemd y reglas de seguridad.

## Mapa web

Abrir:

`webmap/index.html`

La vista web ayuda a detectar errores gruesos de coordenadas y distribución. No sustituye QGIS ni permite crear etiquetas finales.

Para revisar ortofoto PNOA oficial por ventana candidata:

`webmap/pnoa_preview_index.html`

Ese índice solo prepara enlaces/miniaturas WMS. No descarga rasters fuente ni convierte candidatos en entrenamiento.

Cuando existan polígonos aceptados en QGIS, exportar chips PNOA:

```bash
make pnoa-chips
```

Este target ignora puntos candidatos y solo usa `labels_reviewed` / `negative_areas_reviewed` con `review_status=accepted`.
