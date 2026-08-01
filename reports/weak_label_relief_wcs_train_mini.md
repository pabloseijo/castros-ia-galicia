# Weak-label relief WCS export

Generated: 2026-08-01T00:00:00Z

## Scope

- Source manifest: `data/weak-label-splits-v1/weak_label_chip_export_train_mini.tsv`
- Rows selected: 1000
- Coverage: `Elevacion25830_5`
- WCS base: `https://servicios.idee.es/wcs-inspire/mdt`
- Splits filter: `all`

## Files

- Export manifest: `data/weak-label-relief-v1/weak_label_relief_wcs_train_mini.tsv`
- DEM chips: `data/external/weak-label-relief-v1/` (ignored by Git)

## Download Status

- downloaded: 553
- skipped: 447

## DEM Status

- unsupported_country: 447
- valid: 553

## By Split And Role

- train/hard_negative: 554
- train/positive: 446

## Size

- Total local DEM bytes represented by this manifest: 13234510

## Failures

- None.

## Next Step

Run the relief baseline over this manifest and compare it with the RGB ranking, especially the O Val failure on `Castro de Pena Lopesa`.
