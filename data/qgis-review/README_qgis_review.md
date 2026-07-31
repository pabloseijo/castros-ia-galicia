# Paquete QGIS de revisión - Castros IA Galicia

Generado: 2026-07-31

## Qué es

Paquete ligero para abrir en QGIS y pasar del inventario de puntos a etiquetas revisables. No contiene rasters PNOA/LiDAR ni etiquetas arqueológicas finales.

## Archivos principales

- `castros_trasancos_qgis_review.gpkg`: GeoPackage con todas las capas de revisión.
- `review_points.geojson`: 91 puntos con coordenadas.
- `positive_seed_buffers_120m.geojson`: buffers provisionales de positivos train/val/test/test_o_val.
- `tile_windows_512m.geojson`: ventanas candidatas para futuros recortes raster.
- `hard_negative_candidates.geojson`: 160 negativos difíciles generados para revisión.
- `trasancos_aoi.geojson`: caja de trabajo del MVP.
- `qgis_review_tasks.tsv`: cola completa de revisión.
- `geocoding_tasks.tsv`: filas sin coordenadas que hay que resolver antes de usarlas.

## Conteos

- review_points: 91
- positive_seed_buffers_120m: 42
- tile_windows_512m: 42
- hard_negative_candidates: 160
- trasancos_aoi: 1
- qgis_review_tasks: 128
- geocoding_tasks: 37

## Orden de revisión

1. Abrir `castros_trasancos_qgis_review.gpkg` en QGIS.
2. Cargar PNOA/IGN como mapa base y, cuando estén descargados, hillshade/MSRM LiDAR.
3. Resolver primero `P0`: O Val, conflictos tipológicos y filas sin coordenadas.
4. Revisar `positive_seed_buffers_120m`: ajustar a croa/muralla o descartar si el punto cae mal.
5. Revisar `hard_negative_candidates`: aceptar solo negativos visualmente claros.
6. Guardar las decisiones en una capa nueva, no sobrescribir las capas generadas.

## Regla de seguridad

Los buffers de 120 m son semillas geométricas, no perímetros arqueológicos. Sirven para localizar y recortar; la etiqueta final debe salir de revisión visual y fuente contrastada.
