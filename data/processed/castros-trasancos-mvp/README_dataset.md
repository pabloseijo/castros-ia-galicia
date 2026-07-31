# Dataset MVP Castros IA Galicia

Generado: 2026-07-31

## Resumen

- Sitios/pistas en tabla maestra: 127
- Sitios con coordenadas WGS84: 95
- Sitios sin coordenadas: 32
- Candidatos negativos generados para revisar en QGIS: 160

## Particiones

- review_only: 82
- test: 10
- test_o_val: 4
- train: 25
- val: 6

## Usos de dataset

- needs_geocoding: 19
- positive_damaged_review: 16
- positive_o_val_holdout: 4
- review_only: 47
- test_positive_candidate: 10
- train_positive_candidate: 25
- val_positive_candidate: 6

## Municipios

- Fene: 15
- Ferrol: 35
- Narón: 23
- Neda: 6
- San Sadurniño: 18
- Valdoviño: 30

## Lectura operativa

- La salida lista para QGIS está en `castros_trasancos_master.geojson` y `castros_trasancos_master.gpkg`.
- O Val queda como `test_o_val`/holdout cuando hay coordenadas, para no entrenar el primer modelo con el territorio narrativo principal.
- Las filas `review_only`, `needs_geocoding` y `positive_damaged_review` no deben entrar en entrenamiento hasta revisión manual.
- Los negativos generados son solo semillas espaciales para revisar, no negativos arqueológicos confirmados.

## Siguiente ejecución real

1. Abrir el GeoPackage en QGIS.
2. Revisar coordenadas y fusionar duplicados dudosos.
3. Dibujar polígonos/buffers por yacimiento entrenable.
4. Descargar PNOA/LiDAR de CNIG para Trasancos en `/Users/pabloseijo/Documents/CastrosIA/data`.
5. Generar hillshade, slope, LRM/MSRM y recortes 512x512.
