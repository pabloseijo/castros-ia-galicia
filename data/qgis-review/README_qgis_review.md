# Paquete QGIS de revisión - Castros IA Galicia

Generado: 2026-07-31

## Qué es

Paquete ligero para abrir en QGIS y pasar del inventario de puntos a etiquetas revisables. No contiene rasters PNOA/LiDAR ni etiquetas arqueológicas finales.

## Archivos principales

- `castros_trasancos_qgis_review.gpkg`: GeoPackage con todas las capas de revisión.
- `review_points.geojson`: 99 puntos con coordenadas.
- `positive_seed_buffers_120m.geojson`: 48 buffers provisionales de positivos train/val/test/test_o_val.
- `tile_windows_512m.geojson`: 48 ventanas candidatas para futuros recortes raster.
- `pba_geocoding_candidates.geojson`: 17 candidatos oficiales PBA para revisión de geocodificación.
- `hard_negative_candidates.geojson`: 160 negativos difíciles generados para revisión.
- `trasancos_aoi.geojson`: caja de trabajo del MVP.
- `qgis_review_tasks.tsv`: cola completa de revisión.
- `geocoding_tasks.tsv`: filas sin coordenadas que hay que resolver antes de usarlas.

## Conteos

- review_points: 99
- positive_seed_buffers_120m: 48
- tile_windows_512m: 48
- pba_geocoding_candidates: 17
- hard_negative_candidates: 160
- trasancos_aoi: 1
- qgis_review_tasks: 125
- geocoding_tasks: 26

## Orden de revisión

1. Abrir `castros_trasancos_qgis_review.gpkg` en QGIS.
2. Cargar PNOA/IGN como mapa base y, cuando estén descargados, hillshade/MSRM LiDAR.
3. Si existe `pba_geocoding_candidates`, usarla para resolver geocodificación en `geocoded_sites_reviewed`; no copiarla como etiqueta final.
4. Resolver primero `P0`: O Val, conflictos tipológicos y filas sin coordenadas.
5. Revisar `positive_seed_buffers_120m`: ajustar a croa/muralla o descartar si el punto cae mal.
6. Revisar `hard_negative_candidates`: aceptar solo negativos visualmente claros.
7. Guardar las decisiones en una capa nueva, no sobrescribir las capas generadas.

## Regla de seguridad

Los buffers de 120 m son semillas geométricas, no perímetros arqueológicos. Sirven para localizar y recortar; la etiqueta final debe salir de revisión visual y fuente contrastada.
