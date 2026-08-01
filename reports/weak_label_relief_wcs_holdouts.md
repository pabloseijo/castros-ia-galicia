# Weak-label relief WCS export

Generated: 2026-08-01T00:00:00Z

## Scope

- Source manifest: `data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv`
- Rows selected: 204
- Coverage: `Elevacion25830_5`
- WCS base: `https://servicios.idee.es/wcs-inspire/mdt`
- Splits filter: `all`

## Files

- Export manifest: `data/weak-label-relief-v1/weak_label_relief_wcs_holdouts.tsv`
- DEM chips: `data/external/weak-label-relief-v1/` (ignored by Git)

## Download Status

- downloaded: 202
- exists: 2

## DEM Status

- valid: 204

## By Split And Role

- test_o_val/hard_negative: 1
- test_o_val/positive: 4
- test_trasancos/hard_negative: 135
- test_trasancos/positive: 64

## Size

- Total local DEM bytes represented by this manifest: 4938610

## Failures

- None.

## Next Step

Run the relief baseline over this manifest and compare it with the RGB ranking, especially the O Val failure on `Castro de Pena Lopesa`.
