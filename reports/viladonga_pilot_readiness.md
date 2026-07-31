# Viladonga pilot readiness

Generated: 2026-07-31

- Source root: `/Users/pabloseijo/Documents/TFG/img/castroViladonga`
- Label CRS: `EPSG:32629`
- Target CRS: `EPSG:25829`
- Positive polygons: 1
- Negative polygons: 8
- Status: `ready_for_first_pilot`

## Interpretation

Viladonga is a controlled smoke test for the original TFG idea: learn whether the pipeline can export imagery, masks and relief products around a known castro shape. It is not enough for model training by itself.

## Labels

| Feature | Class | Kind | Area m2 | Perimeter m | Circularity | Equivalent diameter m |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 1 | positive | 12913.67 | 413.81 | 0.9477 | 128.23 |
| 2 | 0 | negative | 18815.57 | 583.98 | 0.6933 | 154.78 |
| 3 | 0 | negative | 28108.23 | 763.25 | 0.6063 | 189.18 |
| 4 | 0 | negative | 46389.45 | 982.31 | 0.6041 | 243.03 |
| 5 | 0 | negative | 47299.45 | 967.74 | 0.6347 | 245.40 |
| 6 | 0 | negative | 24549.32 | 1058.32 | 0.2754 | 176.80 |
| 7 | 0 | negative | 45369.38 | 1510.98 | 0.2497 | 240.35 |
| 8 | 0 | negative | 11603.08 | 763.09 | 0.2504 | 121.55 |
| 9 | 0 | negative | 11312.50 | 461.28 | 0.6681 | 120.01 |

## Source Files

- `entrenamiento_viladonga.geojson`: yes (0.01 MB)
- `entrenamiento_castros.gpkg`: yes (0.10 MB)
- `ortofoto/PNOA_MA_OF_ETRS89_HU29_h25_0073_1.tif`: yes (2043.25 MB)
- `LiDAR/PNOA_2009_Lote1_GAL_622-4780_ORT-CLA-COL.laz`: yes (12.37 MB)
- `LiDAR/PNOA_2009_Lote1_GAL_622-4780_ORT-CLA-CIR.laz`: yes (11.36 MB)
- `multiespectrales/2025-04-28-00:00_2025-04-28-23:59_Sentinel-2_L1C_True_color.tiff`: yes (0.12 MB)
- `multiespectrales/2025-04-28-00:00_2025-04-28-23:59_Sentinel-2_L1C_SWIR.tiff`: yes (0.12 MB)
- `multiespectrales/2025-04-28-00:00_2025-04-28-23:59_Sentinel-2_L1C_NDVI.tiff`: yes (0.01 MB)
- `multiespectrales/2025-04-28-00:00_2025-04-28-23:59_Sentinel-2_L1C_Moisture_index.tiff`: yes (0.01 MB)

## Runtime

- Python module `numpy`: missing
- Python module `rasterio`: missing
- Python module `geopandas`: missing
- Python module `shapely`: missing
- Python module `pyproj`: missing
- Python module `laspy`: missing
- Python module `lazrs`: missing
- Command `gdalinfo`: missing
- Command `gdaldem`: missing
- Command `pdal`: missing

## Raster Metadata

- `ortofoto/PNOA_MA_OF_ETRS89_HU29_h25_0073_1.tif`: status=skipped_missing_rasterio
- `multiespectrales/2025-04-28-00:00_2025-04-28-23:59_Sentinel-2_L1C_True_color.tiff`: status=skipped_missing_rasterio
- `multiespectrales/2025-04-28-00:00_2025-04-28-23:59_Sentinel-2_L1C_SWIR.tiff`: status=skipped_missing_rasterio
- `multiespectrales/2025-04-28-00:00_2025-04-28-23:59_Sentinel-2_L1C_NDVI.tiff`: status=skipped_missing_rasterio
- `multiespectrales/2025-04-28-00:00_2025-04-28-23:59_Sentinel-2_L1C_Moisture_index.tiff`: status=skipped_missing_rasterio

## Next Commands

```bash
make viladonga-pnoa-chips
make viladonga-lidar-derivatives
```
