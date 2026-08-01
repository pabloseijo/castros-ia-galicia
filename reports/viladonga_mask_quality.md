# Viladonga mask quality

Generated: 2026-08-01

- Manifest: `data/viladonga-pilot/pnoa_chip_manifest.tsv`
- Output TSV: `data/viladonga-pilot/mask_quality.tsv`
- Rows checked: 9
- OK rows: 9
- Failed rows: 0
- Positive rows: 1
- Negative rows: 8
- Missing images: 0
- Missing masks: 0
- Negative masks with positive pixels: 0
- Positive masks empty: 0
- Status: `ready_for_shape_baseline`

## Positive Mask

- Chip: `viladonga-pnoa-positive-1`
- Positive pixels: 51656
- Mask area: 4.9263% of chip
- BBOX px: `373,387,659,632`
- Centroid px: `511.50,511.50`
- Center offset px: 0.01
- Area m2 from raster mask: 12914.00
- Perimeter m from raster mask: 533.00
- Circularity from raster mask: 0.5712
- Equivalent diameter m from raster mask: 128.23
- QA overlay: `data/viladonga-pilot/chips/pnoa/qa/viladonga-pnoa-positive-1-overlay.png`

## Interpretation

The exported PNOA chips and masks are technically usable for a controlled morphology smoke test if status is `ready_for_shape_baseline`. This only validates the export and mask geometry; it does not prove automatic archaeological discovery and it is not enough data for serious model training.

The raster circularity is computed from pixel-edge perimeter, so it is deliberately conservative and not directly comparable to vector circularity from `reports/viladonga_pilot_readiness.md`. Use it as a mask QA signal, not as the archaeological morphology estimate.

The next defensible step is to compare image and relief features against this verified mask, while the fine LiDAR branch waits for the correct LAZ tiles `630-4780` and `630-4782`.
