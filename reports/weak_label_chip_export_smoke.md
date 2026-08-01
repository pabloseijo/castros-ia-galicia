# Weak-label chip export

Generated: 2026-08-01T00:00:00Z

## Scope

- Source manifest: `data/weak-label-splits-v1/weak_label_tile_manifest_512m.tsv`
- Rows selected: 20
- Requested size: 512x512px
- Splits filter: `train,val,test,test_trasancos,test_o_val`
- Labels filter: `all`
- Sources filter: `all`
- Per split cap: `4`
- Per source cap: `none`
- Global limit: `none`

## Files

- Export manifest: `data/weak-label-splits-v1/weak_label_chip_export_smoke.tsv`
- PNG chips: `data/external/weak-label-chips-v1/` (ignored by Git)

## Download Status

- downloaded: 20

## Image Status

- valid: 20

## By Source

- dgt_ortos2021_rgb: 6
- ign_pnoa_rgb: 14

## By Split And Role

- train/hard_negative: 2
- train/positive: 2
- val/hard_negative: 2
- val/positive: 2
- test/hard_negative: 2
- test/positive: 2
- test_trasancos/hard_negative: 2
- test_trasancos/positive: 2
- test_o_val/hard_negative: 1
- test_o_val/positive: 3

## Size

- Total local PNG bytes represented by this manifest: 10499199

## Failures

- None.

## Next Step

Run the same exporter over `test_o_val` and `test_trasancos`, then export `val` and train a minimal chip classifier/ranker before touching full train.
