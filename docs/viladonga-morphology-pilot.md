# Viladonga morphology pilot

This is the first runnable version of the original TFG idea: use a known castro as a controlled case to export chips, masks and LiDAR relief products before scaling to Trasancos.

## Why Viladonga first

Trasancos is still blocked by QGIS review: candidate points and provisional buffers are not training labels. Viladonga already has one positive polygon and eight negative polygons in the original TFG folder, so it can test the technical pipeline immediately.

This pilot is not a model-quality dataset. It is a smoke test for:

- reading the original TFG geodata;
- exporting PNOA image chips;
- rasterizing a segmentation mask for the known castro outline;
- turning LAZ point clouds into a local DEM;
- generating first morphology products: hillshade, slope and LRM;
- proving the project is about shape detection, not only point collection.

## Commands

From the repo root:

```bash
make viladonga-audit
make viladonga-cnig-lidar-candidates
make viladonga-wcs-dem
make viladonga-relief-wcs
make viladonga-lidar-derivatives
make viladonga-pnoa-chips
make viladonga-mask-quality
make viladonga-shape-baseline
make viladonga-relief-shape-baseline
make viladonga-radial-relief-profile
```

The combined target is:

```bash
make viladonga-pilot
```

## Outputs

- `reports/viladonga_pilot_readiness.md`
- `reports/viladonga_cnig_lidar_candidates.md`
- `reports/viladonga_cnig_lidar_downloads.md`
- `reports/viladonga_lidar_derivatives.md`
- `reports/viladonga_mdt_wcs.md`
- `reports/viladonga_pnoa_chips.md`
- `reports/viladonga_mask_quality.md`
- `reports/viladonga_pnoa_shape_baseline.md`
- `reports/viladonga_relief_shape_baseline.md`
- `reports/viladonga_radial_relief_profile.md`
- `data/viladonga-pilot/labels_manifest.tsv`
- `data/viladonga-pilot/cnig_lidar_candidates.tsv`
- `data/viladonga-pilot/cnig_lidar_downloads.tsv`
- `data/viladonga-pilot/lidar_derivatives_manifest.tsv`
- `data/viladonga-pilot/pnoa_chip_manifest.tsv`
- `data/viladonga-pilot/wcs_dem_manifest.tsv`

Generated chips and LiDAR rasters stay ignored by git:

- `data/viladonga-pilot/chips/`
- `data/viladonga-pilot/lidar/`

## Raspberry use

The Raspberry already has `geopandas`, `rasterio`, `shapely`, `pyproj` and `sklearn`. It may still need `laspy` and `lazrs` for LAZ input:

```bash
python3 -m pip install --user laspy lazrs
```

Sync only the small Viladonga inputs first:

```bash
set -a
. /Users/pabloseijo/Documents/KelteraStudio/Nabia/Keltera-Brain/.env
set +a
rsync -av --exclude 'ortofoto/*.tif' /Users/pabloseijo/Documents/TFG/img/castroViladonga/ "$RASPBERRI_SSH_USER@$RASPBERRI_TAILSCALE_HOST:/home/admin/CastrosIA/data/tfg/castroViladonga/"
```

The PNOA chip target can use IGN WMS if the 2 GB orthoimage is absent. The LAZ derivative target needs the correct LAZ tiles plus labels. If those tiles are missing, `make viladonga-relief-wcs` can use the public MDT5 WCS as a coarse relief baseline.

To locate the official CNIG LAZ tiles for the current chip bounds:

```bash
make viladonga-cnig-lidar-candidates
```

The candidate query is lightweight and writes only a TSV/report. To download the preferred 3rd coverage LAZ files, run:

```bash
python3 scripts/query_viladonga_cnig_lidar.py --coverage LIDA3 --download-dir data/external/viladonga/cnig-lidar-3a
```

Current LAZ status:

- original TFG folder had wrong first-coverage tiles: `622-4780`;
- CNIG query now finds the preferred 2024 third-coverage LAZ tiles for the current chip bounds: `630-4780`, `630-4781`, `631-4780`, `631-4781`;
- Raspberry download path: `/home/admin/CastrosIA/data/viladonga-lidar/cnig-lidar-3a`;
- details: `reports/viladonga_cnig_lidar_candidates.md`, `reports/viladonga_cnig_lidar_downloads.md` and `reports/viladonga_laz_tile_blocker.md`.

## Methodological line

For castro shape, LiDAR derivatives are the primary signal. PNOA is visual texture. Sentinel-2 is auxiliary context for vegetation and moisture, not enough by itself to trace small walls. Hyperspectral data would be useful for buried structures if high-resolution acquisitions become available, but it is not present in the current open-data pilot.
