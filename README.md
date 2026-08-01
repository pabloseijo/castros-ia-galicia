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
- Workspace QGIS de errores weak-label por carriles: `213` tareas, `177` puntos únicos, `30` puntos únicos P0 y capa `p0_pretriage` de primera pasada autónoma.

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
make viladonga-cnig-lidar-candidates
make viladonga-wcs-dem
make viladonga-relief-wcs
make viladonga-lidar-derivatives
make viladonga-pnoa-chips
make viladonga-mask-quality
make viladonga-shape-baseline
make viladonga-relief-shape-baseline
make viladonga-radial-relief-profile
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
make weak-label-error-review-workspace
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
make viladonga-cnig-lidar-candidates
make viladonga-relief-wcs
make viladonga-lidar-derivatives
make viladonga-pnoa-chips
make viladonga-mask-quality
make viladonga-shape-baseline
make viladonga-relief-shape-baseline
make viladonga-radial-relief-profile
```

Documentación: `docs/viladonga-morphology-pilot.md`.

La finalidad es probar chips, máscaras, derivados de relieve y calidad geométrica básica sobre un castro conocido. No es un dataset suficiente para entrenar un modelo serio.

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
- `reports/viladonga_cnig_lidar_candidates.md`: teselas LiDAR CNIG candidatas para sustituir el MDT5 por LAZ fino oficial.
- `reports/viladonga_cnig_lidar_downloads.md`: estado de descarga Raspberry de los LAZ CNIG 3ª cobertura, fuera de Git.
- `reports/viladonga_mdt_wcs.md`: recorte MDT5 por WCS para desbloquear relieve grueso.
- `reports/viladonga_lidar_derivatives.md`: derivados LiDAR/relieve generados para Viladonga.
- `reports/viladonga_laz_tile_blocker.md`: teselas LAZ correctas que faltan para relieve LiDAR fino.
- `reports/viladonga_pnoa_chips.md`: chips PNOA y máscaras de segmentación para Viladonga.
- `reports/viladonga_mask_quality.md`: auditoría de presencia, binariedad y geometría raster de las máscaras Viladonga.
- `reports/viladonga_pnoa_shape_baseline.md`: baseline PNOA de señal de borde/textura contra plantilla de forma castrexa.
- `reports/viladonga_relief_shape_baseline.md`: baseline de forma sobre DEM, slope, hillshade y LRM.
- `reports/viladonga_radial_relief_profile.md`: perfiles/anillos radiales de relieve para separar señal de talud de topografía general.
- `reports/weak_label_error_review_workspace_v1.md`: workspace QGIS por carriles `review_lane`.
- `data/weak-label-error-review-workspace-v1/weak_label_error_review_workspace_v1.gpkg`: capas QGIS `p0_pretriage`, `p0_unique_first_pass`, `lane_mamoa_false_positive`, `lane_mamoa_specialist_positive`, `lane_morphology_rescue`, etc.
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

Para revisar errores weak-label por carriles:

`data/weak-label-error-review-workspace-v1/weak_label_error_review_workspace_v1.gpkg`

Orden práctico dentro del GPKG:

1. `p0_pretriage`
2. `lane_mamoa_false_positive`
3. `lane_mamoa_specialist_positive`
4. `lane_morphology_rescue`

Campos clave: `pretriage_order`, `pretriage_group`, `pretriage_decision`, `review_lane`, `duplicate_count`, `suggested_taxonomy`, `specialist_rank`, `fusion_rank`, `max_safety_rank`.

Cuando existan polígonos aceptados en QGIS, exportar chips PNOA:

```bash
make pnoa-chips
```

Este target ignora puntos candidatos y solo usa `labels_reviewed` / `negative_areas_reviewed` con `review_status=accepted`.
