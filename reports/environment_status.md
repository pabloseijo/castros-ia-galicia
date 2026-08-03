# Environment status

Generated: 2026-07-31

## Summary

- Environment: local
- Base interpreter: `/opt/homebrew/opt/python@3.14/bin/python3.14`
- Geospatial interpreter (GEO_PYTHON): `/Users/pabloseijo/Documents/Mimir/wiki/vida/carrera/arqueologia-computacional/castros-ia-galicia/.venv-geo/bin/python`
- QGIS available: no
- Raster/DTM base processing ready: yes
- LiDAR point-cloud processing ready: yes
- Deep learning experiment ready: no

Readiness is judged against the interpreter each target actually uses.
The Makefile runs every geospatial target through `GEO_PYTHON`, so a
module missing from the base interpreter but present in `.venv-geo` is
not a blocker; it is reported below as a base-only gap.

The light dataset, QGIS package, reports and web map do not require these optional tools.

## Commands

| Tool | Status | Purpose | Path/version |
|---|---|---|---|
| `python3` | available | Python runtime | Python 3.14.6 |
| `qgis` | missing | QGIS desktop |  |
| `qgis_process` | missing | QGIS processing CLI |  |
| `gdalinfo` | available | GDAL raster tools | GDAL 3.13.2 "Iowa City", released 2026/07/20 |
| `ogr2ogr` | available | GDAL/OGR vector tools | GDAL 3.13.2 "Iowa City", released 2026/07/20 |
| `gdaldem` | available | GDAL DEM derivatives | GDAL 3.13.2 "Iowa City", released 2026/07/20 |
| `pdal` | available | PDAL point cloud tools | -------------------------------------------------------------------------------- pdal 2.10.2 (git-version: Release) ---------------------------------------------------------------- |

## Python modules

| Module | Effective | Base | GEO_PYTHON | Purpose | Version |
|---|---|---|---|---|---|
| `numpy` | available | available | available | numeric arrays | 2.0.2 |
| `pandas` | available | missing | available | tabular QA | 2.3.3 |
| `geopandas` | available | missing | available | vector geodata | 1.0.1 |
| `shapely` | available | missing | available | geometry operations | 2.0.7 |
| `pyproj` | available | missing | available | CRS transforms | 3.6.1 |
| `fiona` | available | missing | available | GeoPackage IO | 1.10.1 |
| `rasterio` | available | missing | available | raster windows | 1.4.3 |
| `sklearn` | missing | missing | missing | classical ML baselines |  |
| `torch` | missing | missing | missing | deep learning |  |
| `ultralytics` | missing | missing | missing | YOLO experiments |  |

## Operational blockers

- Manual visual review still requires opening the GeoPackages in QGIS desktop.
- YOLO/deep-learning experiments need a model stack such as PyTorch and Ultralytics.
