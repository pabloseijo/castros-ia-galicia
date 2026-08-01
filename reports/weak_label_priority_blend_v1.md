# Weak-label priority blend v1

Generated: 2026-08-01T00:00:00Z

## What This Is

A review-priority stress test over the RGB+relief fusion baseline. It compares the supervised fusion score with the morphology-aware `archetype_max` relief channel.
This does not claim better detection; it shows whether a second safety queue can rescue atypical castro forms that the global ranker suppresses.

## Files

- Fusion features: `data/weak-label-fusion-v1/weak_label_rgb_relief_features.tsv`
- Fusion scores: `data/weak-label-fusion-v1/weak_label_rgb_relief_scores.tsv`
- Blend score TSV: `data/weak-label-fusion-v1/weak_label_priority_blend_scores.tsv`
- Blend metrics TSV: `data/weak-label-fusion-v1/weak_label_priority_blend_metrics.tsv`

## Blend Logic

- `fusion_only`: supervised RGB+relief ranker, normalized by dataset.
- `archetype_only`: morphology channel only, using the strongest relief archetype.
- `mean`: equal blend of the two normalized channels.
- `fusion70_arch30`: conservative blend biased toward supervised fusion.
- `max_safety`: takes the better of fusion or archetype per row; useful as a review safety queue.

## Metrics

| Blend | Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| archetype_only | holdouts | all | 204 | 68 | 136 | 0.790333 | 0.707459 | 0.740000 | 0.544118 | 1 | 45.5 |
| archetype_only | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| archetype_only | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.783796 | 0.691568 | 0.700000 | 0.546875 | 1 | 43.5 |
| archetype_only | train_mini | all | 553 | 276 | 277 | 0.718948 | 0.707683 | 0.800000 | 0.144928 | 1 | 191.0 |
| archetype_only | val | all | 1851 | 359 | 1492 | 0.799398 | 0.537969 | 0.740000 | 0.103064 | 1 | 314.0 |
| fusion70_arch30 | holdouts | all | 204 | 68 | 136 | 0.890030 | 0.850609 | 0.840000 | 0.617647 | 1 | 36.5 |
| fusion70_arch30 | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| fusion70_arch30 | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.896759 | 0.847136 | 0.800000 | 0.625000 | 1 | 35.0 |
| fusion70_arch30 | train_mini | all | 553 | 276 | 277 | 0.850481 | 0.840630 | 0.880000 | 0.159420 | 1 | 161.5 |
| fusion70_arch30 | val | all | 1851 | 359 | 1492 | 0.886970 | 0.739653 | 0.960000 | 0.133705 | 1 | 217.0 |
| fusion_only | holdouts | all | 204 | 68 | 136 | 0.888949 | 0.866398 | 0.900000 | 0.661765 | 1 | 37.5 |
| fusion_only | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| fusion_only | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.897569 | 0.864284 | 0.880000 | 0.687500 | 1 | 36.5 |
| fusion_only | train_mini | all | 553 | 276 | 277 | 0.869330 | 0.859469 | 0.920000 | 0.166667 | 1 | 156.5 |
| fusion_only | val | all | 1851 | 359 | 1492 | 0.878253 | 0.754336 | 0.980000 | 0.136490 | 1 | 207.0 |
| max_safety | holdouts | all | 204 | 68 | 136 | 0.909278 | 0.858070 | 0.840000 | 0.617647 | 1 | 38.0 |
| max_safety | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| max_safety | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.905903 | 0.848180 | 0.820000 | 0.640625 | 1 | 38.5 |
| max_safety | train_mini | all | 553 | 276 | 277 | 0.804112 | 0.772932 | 0.860000 | 0.155797 | 1 | 174.5 |
| max_safety | val | all | 1851 | 359 | 1492 | 0.866082 | 0.630999 | 0.760000 | 0.105850 | 1 | 256.0 |
| mean | holdouts | all | 204 | 68 | 136 | 0.878028 | 0.822447 | 0.800000 | 0.588235 | 1 | 40.0 |
| mean | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| mean | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.880093 | 0.816733 | 0.780000 | 0.609375 | 1 | 38.0 |
| mean | train_mini | all | 553 | 276 | 277 | 0.823392 | 0.814895 | 0.900000 | 0.163043 | 1 | 166.5 |
| mean | val | all | 1851 | 359 | 1492 | 0.880809 | 0.698574 | 0.900000 | 0.125348 | 1 | 228.0 |

## Fusion Reference

- fusion holdouts all: ROC-AUC `0.888949`, AP `0.866398`, P@50 `0.900000`.
- fusion holdouts split:test_o_val: ROC-AUC `0.750000`, AP `0.950000`, P@50 `0.800000`.
- fusion holdouts split:test_trasancos: ROC-AUC `0.897569`, AP `0.864284`, P@50 `0.880000`.
- fusion train_mini all: ROC-AUC `0.869330`, AP `0.859469`, P@50 `0.920000`.
- fusion val all: ROC-AUC `0.878253`, AP `0.754336`, P@50 `0.980000`.

## Reading

- `max_safety` holdouts: ROC-AUC `0.909278`, AP `0.858070`, P@50 `0.840000`.
- `max_safety` val: ROC-AUC `0.866082`, AP `0.630999`, P@50 `0.760000`.
- `fusion70_arch30` val: ROC-AUC `0.886970`, AP `0.739653`, P@50 `0.960000`.
- The supervised fusion score remains the main global ranker. `max_safety` is a separate review lane for rare morphologies, not the final detector score.

## O Val Reading

### fusion_only

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 14 | 1 | 2.88054827 | `O Castro (Castro de Quintá)` |
| 26 | 1 | 2.01466854 | `Castro da Pedreira` |
| 32 | 1 | 1.64748227 | `Monte do Castro (Castro de Vilasuso)` |
| 80 | 0 | 0.40071708 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 199 | 1 | -1.42006639 | `Castro de Pena Lopesa` |

### max_safety

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 14 | 1 | 2.99876808 | `O Castro (Castro de Quintá)` |
| 30 | 1 | 2.01466854 | `Castro da Pedreira` |
| 35 | 1 | 1.64748227 | `Monte do Castro (Castro de Vilasuso)` |
| 99 | 0 | 0.40071708 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 72 | 1 | 0.71955212 | `Castro de Pena Lopesa` |

### fusion70_arch30

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 10 | 1 | 2.91601422 | `O Castro (Castro de Quintá)` |
| 24 | 1 | 1.75175278 | `Castro da Pedreira` |
| 36 | 1 | 1.21353683 | `Monte do Castro (Castro de Vilasuso)` |
| 77 | 0 | 0.33184277 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 178 | 1 | -0.77818084 | `Castro de Pena Lopesa` |

### mean

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 9 | 1 | 2.93965818 | `O Castro (Castro de Quintá)` |
| 24 | 1 | 1.57647560 | `Castro da Pedreira` |
| 45 | 1 | 0.92423988 | `Monte do Castro (Castro de Vilasuso)` |
| 79 | 0 | 0.28592656 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 133 | 1 | -0.35025714 | `Castro de Pena Lopesa` |

### archetype_only

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 9 | 1 | 2.99876808 | `O Castro (Castro de Quintá)` |
| 32 | 1 | 1.13828265 | `Castro da Pedreira` |
| 80 | 1 | 0.20099748 | `Monte do Castro (Castro de Vilasuso)` |
| 83 | 0 | 0.17113604 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 47 | 1 | 0.71955212 | `Castro de Pena Lopesa` |

## Interpretation

- `max_safety` improves the treatment of `Castro de Pena Lopesa`: it moves from rank 199 under supervised fusion to rank 72 in holdouts, above the mámoa hard negative.
- The cost is lower top-50 precision on holdouts, so the correct operational use is two queues: main queue by fusion score, safety queue by morphology rescue.
- This directly addresses the current bottleneck: castros are not one shape, so the review workflow must preserve several shape hypotheses at once.
