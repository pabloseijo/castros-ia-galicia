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

- Dataset maestro MVP: 128 filas.
- Puntos con coordenadas WGS84: 91.
- Buffers provisionales para revisión: 42.
- Ventanas raster candidatas: 42.
- Negativos difíciles generados para revisión: 160.
- Tareas de geocodificación: 37.

O Val queda como holdout narrativo. No se usa para entrenar en la primera versión.

Split espacial actual:

- `train`: Ferrol, Valdoviño y Neda, 25 positivos candidatos.
- `val`: San Sadurniño, 6 positivos candidatos.
- `test`: Narón no-O-Val, 8 positivos candidatos.
- `test_o_val`: O Val, 3 positivos candidatos.

La auditoría metodológica está en `docs/literature-audit-2026-07-31.md`.

## Estructura

```text
castros-ia-galicia/
├── configs/
├── data/
│   ├── external/          # rasters/LAZ fuera de git
│   ├── processed/         # outputs ligeros reproducibles
│   └── qgis-review/       # paquete QGIS de revisión
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
make verify
```

## Política de datos

Los datos pesados PNOA/LiDAR/Sentinel no se versionan aquí. Deben vivir fuera de la wiki, por ejemplo en:

`/Users/pabloseijo/Documents/CastrosIA/data`

Las capas generadas aquí son ligeras y reproducibles. Los buffers de 120 m son semillas de revisión, no perímetros arqueológicos.

## Siguiente paso real

Abrir `data/qgis-review/castros_trasancos_qgis_review.gpkg` en QGIS, revisar las tareas P0, ajustar buffers a polígonos reales y solo después descargar/procesar rasters para ventanas útiles.
