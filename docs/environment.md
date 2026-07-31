# Entorno local

El MVP ligero funciona con Python estándar:

```bash
make verify
```

Las fases siguientes necesitan herramientas pesadas:

- QGIS para la revisión visual y dibujo de etiquetas.
- GDAL/OGR para cortar y transformar rasters.
- PDAL para procesar nubes LiDAR/LAZ si se trabaja desde punto original.
- `rasterio`, `geopandas`, `shapely` y `pyproj` para automatizar ventanas raster/vector.
- PyTorch/Ultralytics solo cuando ya existan etiquetas revisadas.

Comprobar estado:

```bash
make env-check
```

Reporte generado:

`reports/environment_status.md`

No conviene instalar el stack de modelo antes de tener `labels_reviewed` y `negative_areas_reviewed` con ejemplos aceptados. Primero se revisa, luego se descargan rasters, y solo después se entrena.
