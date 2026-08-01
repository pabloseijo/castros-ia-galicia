# Weak-label chip export

Generated: 2026-08-01T00:00:00Z

## Scope

- Source manifest: `data/weak-label-splits-v1/weak_label_tile_manifest_512m.tsv`
- Rows selected: 1000
- Requested size: 512x512px
- Splits filter: `train`
- Labels filter: `all`
- Sources filter: `all`
- Per split cap: `1000`
- Per source cap: `none`
- Global limit: `none`

## Files

- Export manifest: `data/weak-label-splits-v1/weak_label_chip_export_train_mini.tsv`
- PNG chips: `data/external/weak-label-chips-v1/` (ignored by Git)

## Download Status

- downloaded: 996
- exists: 4

## Image Status

- valid: 1000

## By Source

- dgt_ortos2021_rgb: 447
- ign_pnoa_rgb: 553

## By Split And Role

- train/hard_negative: 554
- train/positive: 446

## Size

- Total local PNG bytes represented by this manifest: 466587856

## Failures

- None.

## Next Step

Use this train-mini sample with the exported `val` and O Val/Trasancos holdouts to run the first RGB baseline/ranker.
