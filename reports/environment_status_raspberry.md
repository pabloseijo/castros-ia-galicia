# Environment status

Generated: 2026-07-31

## Summary

- Environment: raspberry
- QGIS available: no
- Raster/DTM base processing ready: yes
- LiDAR point-cloud processing ready: no
- Deep learning experiment ready: no

The light dataset, QGIS package, reports and web map do not require these optional tools.

## Commands

| Tool | Status | Purpose | Path/version |
|---|---|---|---|
| `python3` | available | Python runtime | Python 3.13.5 |
| `qgis` | missing | QGIS desktop |  |
| `qgis_process` | missing | QGIS processing CLI |  |
| `gdalinfo` | available | GDAL raster tools | GDAL 3.10.3, released 2025/04/01 |
| `ogr2ogr` | available | GDAL/OGR vector tools | GDAL 3.10.3, released 2025/04/01 |
| `gdaldem` | available | GDAL DEM derivatives | GDAL 3.10.3, released 2025/04/01 |
| `pdal` | missing | PDAL point cloud tools |  |

## Python modules

| Module | Status | Purpose | Version |
|---|---|---|---|
| `numpy` | available | numeric arrays | 2.2.4 |
| `pandas` | available | tabular QA | 2.2.3 |
| `geopandas` | available | vector geodata | 1.0.1 |
| `shapely` | available | geometry operations | 2.1.0 |
| `pyproj` | available | CRS transforms | 3.7.1 |
| `fiona` | available | GeoPackage IO | 1.10.1 |
| `rasterio` | available | raster windows | 1.4.3 |
| `sklearn` | available | classical ML baselines | 1.4.2 |
| `torch` | missing | deep learning |  |
| `ultralytics` | missing | YOLO experiments |  |

## Operational blockers

- Manual visual review still requires opening the GeoPackages in QGIS desktop.
- LiDAR point-cloud phase needs PDAL only if processing original LAZ/COPC point clouds instead of prepared DEM/DTM rasters.
- YOLO/deep-learning experiments need a model stack such as PyTorch and Ultralytics.
