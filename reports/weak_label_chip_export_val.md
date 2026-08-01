# Weak-label chip export

Generated: 2026-08-01T00:00:00Z

## Scope

- Source manifest: `data/weak-label-splits-v1/weak_label_tile_manifest_512m.tsv`
- Rows selected: 2037
- Requested size: 512x512px
- Splits filter: `val`
- Labels filter: `all`
- Sources filter: `all`
- Per split cap: `none`
- Per source cap: `none`
- Global limit: `none`

## Files

- Export manifest: `data/weak-label-splits-v1/weak_label_chip_export_val.tsv`
- PNG chips: `data/external/weak-label-chips-v1/` (ignored by Git)

## Download Status

- downloaded: 1
- exists: 2036

## Image Status

- valid: 2037

## By Source

- dgt_ortos2021_rgb: 186
- ign_pnoa_rgb: 1851

## By Split And Role

- val/hard_negative: 1612
- val/positive: 425

## Size

- Total local PNG bytes represented by this manifest: 1243284092

## Failures

- None.

## Next Step

Train the first minimal chip classifier/ranker and evaluate it against `test_o_val` and `test_trasancos` before exporting full train.
