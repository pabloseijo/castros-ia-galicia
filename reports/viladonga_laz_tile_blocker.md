# Viladonga LAZ tile blocker

Generated: 2026-07-31

## Status

- Status: `blocked_wrong_laz_tiles`
- Workaround ready: `reports/viladonga_mdt_wcs.md` and `reports/viladonga_lidar_derivatives.md`

## What happened

The original TFG folder contains two LAZ files:

- `PNOA_2009_Lote1_GAL_622-4780_ORT-CLA-COL.laz`
- `PNOA_2009_Lote1_GAL_622-4780_ORT-CLA-CIR.laz`

Their header bounds are:

- x: `622000.00` to `623999.99`
- y: `4778000.00` to `4779999.99`

The buffered Viladonga pilot bounds needed for labels and relief are:

- x: `630124.94` to `631778.48`
- y: `4779112.40` to `4780625.86`

So the LAZ files in the folder do not overlap the annotated castro.

## Required CNIG 2 km tiles

The tile naming pattern in the available files is west-km plus north-km. For the buffered Viladonga bounds, the required 2 km tile ids are:

- `630-4780`
- `630-4782`

Likely first-coverage filenames to look for:

- `PNOA_2009_Lote1_GAL_630-4780_ORT-CLA-COL.laz`
- `PNOA_2009_Lote1_GAL_630-4782_ORT-CLA-COL.laz`

Equivalent newer PNOA-LiDAR/MDT products are also acceptable if they cover the same extent.

## Current workaround

The project now fetches a public WCS MDT5 crop from `https://servicios.idee.es/wcs-inspire/mdt` and derives:

- DEM
- hillshade 315/45
- slope degrees
- LRM

This is good enough to start the morphology branch and validate scripts, but not fine enough to be the final archaeological LiDAR signal.
