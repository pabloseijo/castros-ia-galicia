# Weak-label relief WCS export

Generated: 2026-08-01T00:00:00Z

## Scope

- Source manifest: `data/weak-label-splits-v1/weak_label_chip_export_test.tsv`
- Rows selected: 2530
- Coverage: `Elevacion25830_5`
- WCS base: `https://servicios.idee.es/wcs-inspire/mdt`
- Splits filter: `all`

## Files

- Export manifest: `data/weak-label-relief-v1/weak_label_relief_wcs_test.tsv`
- DEM chips: `data/external/weak-label-relief-v1/` (ignored by Git)

## Download Status

- downloaded: 2383
- skipped: 147

## DEM Status

- unsupported_country: 147
- valid: 2383

## By Split And Role

- test/hard_negative: 1966
- test/positive: 564

## Size

- Total local DEM bytes represented by this manifest: 57301404

## Failures

- None.

## Next Step

Run the relief baseline over this manifest and compare it with the RGB ranking, especially the O Val failure on `Castro de Pena Lopesa`.
