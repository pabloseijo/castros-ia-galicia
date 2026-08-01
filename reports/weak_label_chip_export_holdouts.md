# Weak-label chip export

Generated: 2026-08-01T00:00:00Z

## Scope

- Source manifest: `data/weak-label-splits-v1/weak_label_tile_manifest_512m.tsv`
- Rows selected: 204
- Requested size: 512x512px
- Splits filter: `test_o_val,test_trasancos`
- Labels filter: `all`
- Sources filter: `all`
- Per split cap: `none`
- Per source cap: `none`
- Global limit: `none`

## Files

- Export manifest: `data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv`
- PNG chips: `data/external/weak-label-chips-v1/` (ignored by Git)

## Download Status

- downloaded: 196
- exists: 8

## Image Status

- valid: 204

## By Source

- ign_pnoa_rgb: 204

## By Split And Role

- test_trasancos/hard_negative: 135
- test_trasancos/positive: 64
- test_o_val/hard_negative: 1
- test_o_val/positive: 4

## Size

- Total local PNG bytes represented by this manifest: 132585969

## Failures

- None.

## Next Step

Export `val`, then train a minimal chip classifier/ranker and evaluate it against the already exported O Val/Trasancos holdouts.
