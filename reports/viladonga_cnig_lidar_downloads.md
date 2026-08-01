# Viladonga CNIG LiDAR downloads

Generated: 2026-08-01

- Chip manifest: `data/viladonga-pilot/pnoa_chip_manifest.tsv`
- Output TSV: `data/viladonga-pilot/cnig_lidar_downloads.tsv`
- Official source: `https://centrodedescargas.cnig.es/CentroDescargas/lidar-tercera-cobertura`
- Product definitions: `https://pnoa.ign.es/pnoa-lidar/productos-a-descarga`
- Pilot chip bounds EPSG:25829: `630239.88,4779224.99,631641.93,4780504.99`
- Queried 1 km cells from lower-left IDs: 630-4779, 630-4780, 631-4779, 631-4780
- Preferred status: `downloaded_lida3`

## Preferred 3rd coverage LAZ

| File | Sec | Query lower tile | Year | Density | Size MB | Init status |
|---|---:|---|---:|---|---:|---|
| `PNOA_2024_GAL_630-4780_H29_NPC01.laz` | 12726608 | `630-4779` | 2024 | 5 ptos/m2 | 57.97 | `ready_no_interactive_license` |
| `PNOA_2024_GAL_630-4781_H29_NPC01.laz` | 12735925 | `630-4780` | 2024 | 5 ptos/m2 | 66.42 | `ready_no_interactive_license` |
| `PNOA_2024_GAL_631-4780_H29_NPC01.laz` | 12731455 | `631-4779` | 2024 | 5 ptos/m2 | 72.65 | `ready_no_interactive_license` |
| `PNOA_2024_GAL_631-4781_H29_NPC01.laz` | 12755297 | `631-4780` | 2024 | 5 ptos/m2 | 61.87 | `ready_no_interactive_license` |

Approximate preferred download size: `258.91 MB`.

CNIG's 3rd-coverage filenames here use the northern kilometre edge for the Y component: for example, the query point inside lower cell `630-4779` returns `630-4780`.

## Fallback coverages

- 2nd coverage: not queried in this run.
- 1st coverage: not queried in this run.

## Download command

The script does not download heavy LAZ by default. To download only the preferred 3rd-coverage files into the ignored external-data area:

```bash
python3 scripts/query_viladonga_cnig_lidar.py --coverage LIDA3 --download-dir data/external/viladonga/cnig-lidar-3a
```

Each download is a POST to `https://centrodedescargas.cnig.es/CentroDescargas/descargaDir` with `secDescDirLA=<sec>` after `initDescargaDir` confirms no interactive licence step.

## Interpretation

This resolves the previous LAZ blocker for Viladonga. If the preferred files are already downloaded, the next morphology step is to rebuild the DEM/relief derivatives from point cloud data and rerun the relief/radial baselines against the MDT5 WCS results.
