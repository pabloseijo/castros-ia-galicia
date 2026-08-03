# Weak-label priority blend v1

Generated: 2026-08-01T00:00:00Z

## What This Is

A review-priority stress test over the RGB+relief fusion baseline. It compares the supervised fusion score with the morphology-aware `archetype_max` relief channel.
This does not claim better detection; it shows whether a second safety queue can rescue atypical castro forms that the global ranker suppresses.

## Files

- Fusion features: `data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_features.tsv`
- Fusion scores: `data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_scores.tsv`
- Blend score TSV: `data/weak-label-fusion-v1/weak_label_priority_blend_msrm_full_scores.tsv`
- Blend metrics TSV: `data/weak-label-fusion-v1/weak_label_priority_blend_msrm_full_metrics.tsv`

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
| fusion70_arch30 | holdouts | all | 204 | 68 | 136 | 0.917820 | 0.860842 | 0.840000 | 0.617647 | 1 | 35.5 |
| fusion70_arch30 | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| fusion70_arch30 | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.916319 | 0.851872 | 0.780000 | 0.609375 | 1 | 35.0 |
| fusion70_arch30 | test | all | 2383 | 528 | 1855 | 0.910985 | 0.767764 | 0.940000 | 0.089015 | 1 | 318.5 |
| fusion70_arch30 | train | all | 8641 | 1844 | 6797 | 0.921344 | 0.791697 | 0.960000 | 0.026030 | 1 | 1074.5 |
| fusion70_arch30 | val | all | 1851 | 359 | 1492 | 0.916526 | 0.767306 | 0.920000 | 0.128134 | 1 | 210.0 |
| fusion_only | holdouts | all | 204 | 68 | 136 | 0.944312 | 0.909383 | 0.900000 | 0.661765 | 1 | 35.5 |
| fusion_only | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| fusion_only | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.947917 | 0.907557 | 0.880000 | 0.687500 | 1 | 33.5 |
| fusion_only | test | all | 2383 | 528 | 1855 | 0.925436 | 0.812968 | 1.000000 | 0.094697 | 1 | 302.5 |
| fusion_only | train | all | 8641 | 1844 | 6797 | 0.932440 | 0.829662 | 1.000000 | 0.027115 | 1 | 1036.5 |
| fusion_only | val | all | 1851 | 359 | 1492 | 0.927349 | 0.799049 | 0.960000 | 0.133705 | 1 | 200.0 |
| max_safety | holdouts | all | 204 | 68 | 136 | 0.903330 | 0.830729 | 0.760000 | 0.558824 | 1 | 40.5 |
| max_safety | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| max_safety | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.898611 | 0.815204 | 0.740000 | 0.578125 | 1 | 39.0 |
| max_safety | test | all | 2383 | 528 | 1855 | 0.892131 | 0.697323 | 0.840000 | 0.079545 | 1 | 349.0 |
| max_safety | train | all | 8641 | 1844 | 6797 | 0.907437 | 0.736534 | 0.900000 | 0.024403 | 1 | 1145.0 |
| max_safety | val | all | 1851 | 359 | 1492 | 0.895609 | 0.694859 | 0.800000 | 0.111421 | 1 | 233.0 |
| mean | holdouts | all | 204 | 68 | 136 | 0.888408 | 0.819240 | 0.780000 | 0.573529 | 1 | 40.5 |
| mean | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| mean | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.884954 | 0.807330 | 0.720000 | 0.562500 | 1 | 38.5 |
| mean | test | all | 2383 | 528 | 1855 | 0.888608 | 0.716510 | 0.920000 | 0.087121 | 1 | 338.5 |
| mean | train | all | 8641 | 1844 | 6797 | 0.902651 | 0.745171 | 0.940000 | 0.025488 | 1 | 1134.5 |
| mean | val | all | 1851 | 359 | 1492 | 0.898607 | 0.721334 | 0.920000 | 0.128134 | 1 | 228.0 |

## Fusion Reference

- fusion holdouts all: ROC-AUC `0.944312`, AP `0.909383`, P@50 `0.900000`.
- fusion holdouts split:test_o_val: ROC-AUC `0.750000`, AP `0.950000`, P@50 `0.800000`.
- fusion holdouts split:test_trasancos: ROC-AUC `0.947917`, AP `0.907557`, P@50 `0.880000`.
- fusion test all: ROC-AUC `0.925436`, AP `0.812968`, P@50 `1.000000`.
- fusion train all: ROC-AUC `0.932440`, AP `0.829662`, P@50 `1.000000`.
- fusion val all: ROC-AUC `0.927349`, AP `0.799049`, P@50 `0.960000`.

## Reading

- `max_safety` holdouts: ROC-AUC `0.903330`, AP `0.830729`, P@50 `0.760000`.
- `max_safety` val: ROC-AUC `0.895609`, AP `0.694859`, P@50 `0.800000`.
- `fusion70_arch30` val: ROC-AUC `0.916526`, AP `0.767306`, P@50 `0.920000`.
- The supervised fusion score remains the main global ranker. `max_safety` is a separate review lane for rare morphologies, not the final detector score.

## O Val Reading

### fusion_only

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 4 | 1 | 2.97240309 | `O Castro (Castro de Quintá)` |
| 24 | 1 | 1.83501748 | `Castro da Pedreira` |
| 16 | 1 | 2.09704242 | `Monte do Castro (Castro de Vilasuso)` |
| 110 | 0 | -0.04242787 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 131 | 1 | -0.35337642 | `Castro de Pena Lopesa` |

### max_safety

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 12 | 1 | 2.97240309 | `O Castro (Castro de Quintá)` |
| 24 | 1 | 2.02669014 | `Castro da Pedreira` |
| 22 | 1 | 2.09704242 | `Monte do Castro (Castro de Vilasuso)` |
| 120 | 0 | 0.06063517 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 61 | 1 | 1.16572288 | `Castro de Pena Lopesa` |

### fusion70_arch30

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 5 | 1 | 2.93589677 | `O Castro (Castro de Quintá)` |
| 20 | 1 | 1.89251928 | `Castro da Pedreira` |
| 28 | 1 | 1.54665259 | `Monte do Castro (Castro de Vilasuso)` |
| 108 | 0 | -0.01150896 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 98 | 1 | 0.10235337 | `Castro de Pena Lopesa` |

### mean

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 8 | 1 | 2.91155921 | `O Castro (Castro de Quintá)` |
| 20 | 1 | 1.93085381 | `Castro da Pedreira` |
| 40 | 1 | 1.17972603 | `Monte do Castro (Castro de Vilasuso)` |
| 103 | 0 | 0.00910365 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 76 | 1 | 0.40617323 | `Castro de Pena Lopesa` |

### archetype_only

| Rank | Class | Score | Name |
|---:|---:|---:|---|
| 12 | 1 | 2.85071533 | `O Castro (Castro de Quintá)` |
| 19 | 1 | 2.02669014 | `Castro da Pedreira` |
| 88 | 1 | 0.26240964 | `Monte do Castro (Castro de Vilasuso)` |
| 97 | 0 | 0.06063517 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 46 | 1 | 1.16572288 | `Castro de Pena Lopesa` |

## Interpretation

- `max_safety` tests the treatment of `Castro de Pena Lopesa`: supervised fusion rank `131`, `max_safety` rank `61`; local mámoa `max_safety` rank `120`.
- The cost is lower top-50 precision on holdouts, so the correct operational use is two queues: main queue by fusion score, safety queue by morphology rescue.
- This directly addresses the current bottleneck: castros are not one shape, so the review workflow must preserve several shape hypotheses at once.
