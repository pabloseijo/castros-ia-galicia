# Environment status

Generated: 2026-07-31

## Summary

- Environment: local
- QGIS available: no
- Raster/DTM base processing ready: no
- LiDAR point-cloud processing ready: yes
- Deep learning experiment ready: no

The light dataset, QGIS package, reports and web map do not require these optional tools.

## Commands

| Tool | Status | Purpose | Path/version |
|---|---|---|---|
| `python3` | available | Python runtime | Python 3.9.6 |
| `qgis` | missing | QGIS desktop |  |
| `qgis_process` | missing | QGIS processing CLI |  |
| `gdalinfo` | available | GDAL raster tools | GDAL 3.13.2 "Iowa City", released 2026/07/20 |
| `ogr2ogr` | available | GDAL/OGR vector tools | GDAL 3.13.2 "Iowa City", released 2026/07/20 |
| `gdaldem` | available | GDAL DEM derivatives | GDAL 3.13.2 "Iowa City", released 2026/07/20 |
| `pdal` | available | PDAL point cloud tools | -------------------------------------------------------------------------------- pdal 2.10.2 (git-version: Release) ---------------------------------------------------------------- |

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
- Raster/DTM phase needs GDAL plus Python geospatial libraries before cutting image or DEM tiles.
- YOLO/deep-learning experiments need a model stack such as PyTorch and Ultralytics.
