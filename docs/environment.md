# Entorno local

El MVP ligero funciona con Python estándar:

```bash
make verify
```

Las fases siguientes necesitan herramientas pesadas:

- QGIS para la revisión visual y dibujo de etiquetas.
- GDAL/OGR para cortar y transformar ortofoto, DEM/DTM y derivados raster.
- PDAL solo para procesar nubes LiDAR/LAZ/COPC desde punto original; si usamos DEM/DTM ya preparado, GDAL basta para empezar.
- `rasterio`, `geopandas`, `shapely` y `pyproj` para automatizar ventanas raster/vector.
- PyTorch/Ultralytics solo cuando ya existan etiquetas revisadas.

Comprobar estado:

```bash
make env-check
```

Reporte local generado:

`reports/environment_status.md`

El agente remoto de Raspberry escribe su propio reporte para no mezclar entornos:

`reports/environment_status_raspberry.md`

No conviene instalar el stack de modelo antes de tener `labels_reviewed` y `negative_areas_reviewed` con ejemplos aceptados. Primero se revisa, luego se descargan rasters, y solo después se entrena.

## Estado Raspberry 2026-07-31

Instalado por `apt` en Debian 13 arm64:

- `gdal-bin`
- `python3-gdal`
- `python3-pandas`
- `python3-geopandas`
- `python3-rasterio`
- `python3-shapely`
- `python3-pyproj`
- `python3-fiona`
- `python3-sklearn`

Resultado: la Raspberry queda lista para raster/DTM base con GDAL y Rasterio. PDAL no quedó disponible por apt en esta instalación; se reserva para una fase posterior si se decide procesar LAZ/COPC originales en vez de DEM/DTM raster ya preparado.
