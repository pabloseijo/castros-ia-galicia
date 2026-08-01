# Weak-label priority blend v1

Generated: 2026-08-01T00:00:00Z

## What This Is

A review-priority stress test over the RGB+relief fusion baseline. It compares the supervised fusion score with the morphology-aware `archetype_max` relief channel.
This does not claim better detection; it shows whether a second safety queue can rescue atypical castro forms that the global ranker suppresses.

## Files

- Fusion features: `data/weak-label-fusion-v1/weak_label_rgb_relief_full_features.tsv`
- Fusion scores: `data/weak-label-fusion-v1/weak_label_rgb_relief_full_scores.tsv`
- Blend score TSV: `data/weak-label-fusion-v1/weak_label_priority_blend_full_scores.tsv`
- Blend metrics TSV: `data/weak-label-fusion-v1/weak_label_priority_blend_full_metrics.tsv`

## Blend Logic

- `fusion_only`: supervised RGB+relief ranker, normalized by dataset.
- `archetype_only`: morphology channel only, using the strongest relief archetype.
- `mean`: equal blend of the two normalized channels.
- `fusion70_arch30`: conservative blend biased toward supervised fusion.
- `max_safety`: takes the better of fusion or archetype per row; useful as a review safety queue.

## Metrics

| Blend | Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| archetype_only | holdouts | all | 204 | 68 | 136 | 0.777898 | 0.706531 | 0.640000 | 0.470588 | 1 | 55.5 |
| archetype_only | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| archetype_only | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.770486 | 0.689640 | 0.580000 | 0.453125 | 1 | 54.5 |
| archetype_only | test | all | 2383 | 528 | 1855 | 0.789519 | 0.570808 | 0.820000 | 0.077652 | 1 | 440.0 |
| archetype_only | train | all | 8641 | 1844 | 6797 | 0.811846 | 0.598607 | 0.900000 | 0.024403 | 1 | 1478.5 |
| archetype_only | val | all | 1851 | 359 | 1492 | 0.814298 | 0.581118 | 0.800000 | 0.111421 | 1 | 297.0 |
| fusion70_arch30 | holdouts | all | 204 | 68 | 136 | 0.903330 | 0.839886 | 0.820000 | 0.602941 | 1 | 38.5 |
| fusion70_arch30 | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| fusion70_arch30 | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.907060 | 0.833381 | 0.780000 | 0.609375 | 1 | 36.5 |
| fusion70_arch30 | test | all | 2383 | 528 | 1855 | 0.897981 | 0.743006 | 0.920000 | 0.087121 | 1 | 331.5 |
| fusion70_arch30 | train | all | 8641 | 1844 | 6797 | 0.907792 | 0.762320 | 0.960000 | 0.026030 | 1 | 1104.0 |
| fusion70_arch30 | val | all | 1851 | 359 | 1492 | 0.900780 | 0.739399 | 0.940000 | 0.130919 | 1 | 215.0 |
| fusion_only | holdouts | all | 204 | 68 | 136 | 0.925281 | 0.880837 | 0.880000 | 0.647059 | 1 | 36.5 |
| fusion_only | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| fusion_only | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.935764 | 0.879315 | 0.840000 | 0.656250 | 1 | 34.5 |
| fusion_only | test | all | 2383 | 528 | 1855 | 0.910299 | 0.774873 | 0.940000 | 0.089015 | 1 | 312.5 |
| fusion_only | train | all | 8641 | 1844 | 6797 | 0.916019 | 0.793529 | 1.000000 | 0.027115 | 1 | 1057.5 |
| fusion_only | val | all | 1851 | 359 | 1492 | 0.905931 | 0.759620 | 0.940000 | 0.130919 | 1 | 206.0 |
| max_safety | holdouts | all | 204 | 68 | 136 | 0.888408 | 0.803219 | 0.740000 | 0.544118 | 1 | 44.0 |
| max_safety | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| max_safety | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.883796 | 0.789117 | 0.720000 | 0.562500 | 1 | 42.0 |
| max_safety | test | all | 2383 | 528 | 1855 | 0.878640 | 0.677122 | 0.880000 | 0.083333 | 1 | 363.0 |
| max_safety | train | all | 8641 | 1844 | 6797 | 0.891219 | 0.710325 | 0.900000 | 0.024403 | 1 | 1182.5 |
| max_safety | val | all | 1851 | 359 | 1492 | 0.877126 | 0.658915 | 0.800000 | 0.111421 | 1 | 239.0 |
| mean | holdouts | all | 204 | 68 | 136 | 0.877703 | 0.803166 | 0.780000 | 0.573529 | 1 | 41.5 |
| mean | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| mean | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.876273 | 0.793347 | 0.760000 | 0.593750 | 1 | 39.5 |
| mean | test | all | 2383 | 528 | 1855 | 0.876774 | 0.702578 | 0.900000 | 0.085227 | 1 | 341.5 |
| mean | train | all | 8641 | 1844 | 6797 | 0.890984 | 0.724934 | 0.940000 | 0.025488 | 1 | 1170.0 |
| mean | val | all | 1851 | 359 | 1492 | 0.885699 | 0.703299 | 0.920000 | 0.128134 | 1 | 234.0 |

## Fusion Reference

- fusion holdouts all: ROC-AUC `0.925281`, AP `0.880837`, P@50 `0.880000`.
- fusion holdouts split:test_o_val: ROC-AUC `0.750000`, AP `0.950000`, P@50 `0.800000`.
- fusion holdouts split:test_trasancos: ROC-AUC `0.935764`, AP `0.879315`, P@50 `0.840000`.
- fusion test all: ROC-AUC `0.910299`, AP `0.774873`, P@50 `0.940000`.
- fusion train all: ROC-AUC `0.916019`, AP `0.793529`, P@50 `1.000000`.
- fusion val all: ROC-AUC `0.905931`, AP `0.759620`, P@50 `0.940000`.

## Reading

- `max_safety` holdouts: ROC-AUC `0.888408`, AP `0.803219`, P@50 `0.740000`.
- `max_safety` val: ROC-AUC `0.877126`, AP `0.658915`, P@50 `0.800000`.
- `fusion70_arch30` val: ROC-AUC `0.900780`, AP `0.739399`, P@50 `0.940000`.
- The supervised fusion score remains the main global ranker. `max_safety` is a separate review lane for rare morphologies, not the final detector score.

## O Val Reading

### fusion_only

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 16 | 1 | 2.03245727 | `O Castro (Castro de Quintá)` |
| 17 | 1 | 1.99193191 | `Castro da Pedreira` |
| 33 | 1 | 1.35654451 | `Monte do Castro (Castro de Vilasuso)` |
| 114 | 0 | -0.19504059 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 201 | 1 | -1.23449847 | `Castro de Pena Lopesa` |

### max_safety

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 13 | 1 | 2.85071533 | `O Castro (Castro de Quintá)` |
| 22 | 1 | 2.02669014 | `Castro da Pedreira` |
| 46 | 1 | 1.35654451 | `Monte do Castro (Castro de Vilasuso)` |
| 122 | 0 | 0.06063517 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 55 | 1 | 1.16572288 | `Castro de Pena Lopesa` |

### fusion70_arch30

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 14 | 1 | 2.27793469 | `O Castro (Castro de Quintá)` |
| 19 | 1 | 2.00235938 | `Castro da Pedreira` |
| 41 | 1 | 1.02830405 | `Monte do Castro (Castro de Vilasuso)` |
| 115 | 0 | -0.11833786 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 153 | 1 | -0.51443207 | `Castro de Pena Lopesa` |

### mean

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 14 | 1 | 2.44158630 | `O Castro (Castro de Quintá)` |
| 19 | 1 | 2.00931103 | `Castro da Pedreira` |
| 54 | 1 | 0.80947707 | `Monte do Castro (Castro de Vilasuso)` |
| 110 | 0 | -0.06720271 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 107 | 1 | -0.03438780 | `Castro de Pena Lopesa` |

### archetype_only

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 12 | 1 | 2.85071533 | `O Castro (Castro de Quintá)` |
| 19 | 1 | 2.02669014 | `Castro da Pedreira` |
| 88 | 1 | 0.26240964 | `Monte do Castro (Castro de Vilasuso)` |
| 97 | 0 | 0.06063517 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 46 | 1 | 1.16572288 | `Castro de Pena Lopesa` |

## Interpretation

- `max_safety` tests the treatment of `Castro de Pena Lopesa`: supervised fusion rank `201`, `max_safety` rank `55`; local mámoa `max_safety` rank `122`.
- The cost is lower top-50 precision on holdouts, so the correct operational use is two queues: main queue by fusion score, safety queue by morphology rescue.
- This directly addresses the current bottleneck: castros are not one shape, so the review workflow must preserve several shape hypotheses at once.
