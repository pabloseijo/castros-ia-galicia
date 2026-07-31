# Environment status

Generated: 2026-07-31

## Summary

- QGIS available: no
- Raster/LiDAR processing ready: no
- Deep learning experiment ready: no

The light dataset, QGIS package, reports and web map do not require these optional tools.

## Commands

| Tool | Status | Purpose | Path/version |
|---|---|---|---|
| `python3` | available | Python runtime | Python 3.9.6 |
| `qgis` | missing | QGIS desktop |  |
| `qgis_process` | missing | QGIS processing CLI |  |
| `gdalinfo` | missing | GDAL raster tools |  |
| `ogr2ogr` | missing | GDAL/OGR vector tools |  |
| `gdaldem` | missing | GDAL DEM derivatives |  |
| `pdal` | missing | PDAL point cloud tools |  |

## Python modules

| Module | Status | Purpose | Version |
|---|---|---|---|
| `numpy` | missing | numeric arrays |  |
| `pandas` | missing | tabular QA |  |
| `geopandas` | missing | vector geodata |  |
| `shapely` | missing | geometry operations |  |
| `pyproj` | missing | CRS transforms |  |
| `fiona` | missing | GeoPackage IO |  |
| `rasterio` | missing | raster windows |  |
| `sklearn` | missing | classical ML baselines |  |
| `torch` | missing | deep learning |  |
| `ultralytics` | missing | YOLO experiments |  |

## Operational blockers

- Manual visual review still requires opening the GeoPackages in QGIS desktop.
- Raster/LiDAR phase needs GDAL/PDAL plus Python geospatial libraries before downloading and cutting tiles.
- YOLO/deep-learning experiments need a model stack such as PyTorch and Ultralytics.
