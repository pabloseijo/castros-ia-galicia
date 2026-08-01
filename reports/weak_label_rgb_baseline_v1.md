# Weak-label RGB baseline v1

Generated: 2026-08-01T00:00:00Z

## What This Is

Minimal RGB chip classifier/ranker over weak labels. It uses handcrafted color/edge/ring features and a small logistic regression implemented with numpy.
It is a modelling sanity check, not an archaeological detector.

## Files

- Train manifest: `data/weak-label-splits-v1/weak_label_chip_export_train_mini.tsv`
- Eval manifests: `data/weak-label-splits-v1/weak_label_chip_export_val.tsv`, `data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv`
- Feature table: `data/weak-label-baseline-v1/weak_label_rgb_baseline_features.tsv`
- Score table: `data/weak-label-baseline-v1/weak_label_rgb_baseline_scores.tsv`
- Metrics table: `data/weak-label-baseline-v1/weak_label_rgb_baseline_metrics.tsv`
- Model weights JSON: `data/weak-label-baseline-v1/weak_label_rgb_baseline_model.json`

## Training Setup

- Feature image size: 192x192px
- Radius mode: `fixed`
- Fixed feature radius: 120.0 m
- Logistic epochs: 900
- Learning rate: 0.06
- L2: 0.01
- Final train loss: 0.637835
- Signal status: `weak_rgb_ranking_signal_present`

## Feature Extraction

- ok: 3241

## Dataset Counts

- holdouts: 204 rows (68 positives, 136 hard negatives)
- train_mini: 1000 rows (446 positives, 554 hard negatives)
- val: 2037 rows (425 positives, 1612 hard negatives)

## Metrics

| Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| holdouts | all | 204 | 68 | 136 | 0.710748 | 0.633197 | 0.680000 | 0.500000 | 1 | 52.0 |
| holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| holdouts | split:test_trasancos | 199 | 64 | 135 | 0.715741 | 0.631740 | 0.660000 | 0.515625 | 1 | 48.5 |
| holdouts | source:ign_pnoa_rgb | 204 | 68 | 136 | 0.710748 | 0.633197 | 0.680000 | 0.500000 | 1 | 52.0 |
| train_mini | all | 1000 | 446 | 554 | 0.683160 | 0.623365 | 0.820000 | 0.091928 | 1 | 381.5 |
| train_mini | source:dgt_ortos2021_rgb | 447 | 170 | 277 | 0.725632 | 0.599590 | 0.680000 | 0.200000 | 1 | 142.0 |
| train_mini | source:ign_pnoa_rgb | 553 | 276 | 277 | 0.653233 | 0.659380 | 0.820000 | 0.148551 | 1 | 217.5 |
| val | all | 2037 | 425 | 1612 | 0.681073 | 0.381901 | 0.600000 | 0.070588 | 1 | 587.0 |
| val | source:dgt_ortos2021_rgb | 186 | 66 | 120 | 0.699621 | 0.526421 | 0.580000 | 0.439394 | 3 | 57.0 |
| val | source:ign_pnoa_rgb | 1851 | 359 | 1492 | 0.716841 | 0.396769 | 0.600000 | 0.083565 | 1 | 476.0 |

## Top Holdout Scores

### holdouts

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test_trasancos | 1 | 0.79859539 | `Castro de Vilarrube/Os Castros de Ferreirías` | Valdoviño |
| 2 | test_trasancos | 1 | 0.76279636 | `Castro de Vilasanche` | Ferrol |
| 3 | test_trasancos | 1 | 0.74455425 | `Castro de Tralocastro` | Ferrol |
| 4 | test_trasancos | 1 | 0.74450176 | `A Croa do Castro` | San Sadurniño |
| 5 | test_trasancos | 1 | 0.73644410 | `Castro de Aviño` | Valdoviño |
| 6 | test_trasancos | 0 | 0.72794184 | `Mámoa de Rioboo 1/Mámoa de Canteiros 1` | Valdoviño |
| 7 | test_trasancos | 1 | 0.72603786 | `Castro de Eiravedra` | Narón |
| 8 | test_trasancos | 1 | 0.72530470 | `Castro da Revolta` | Narón |
| 9 | test_trasancos | 1 | 0.70582048 | `Castro` | Valdoviño |
| 10 | test_trasancos | 1 | 0.70280131 | `Castro de Rupiallo` | San Sadurniño |

### val

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | val | 1 | 0.87789323 | `Castro de Mazo de Lagúas/Os Castros` | A Fonsagrada |
| 2 | val | 0 | 0.87213908 | `O Castelo` | O Vicedo |
| 3 | val | 1 | 0.86163000 | `Castro de Novefontes/Castro da Croa/O Castro` | Touro |
| 4 | val | 1 | 0.84630023 | `Castro de Baiobre de Branzá` | Touro |
| 5 | val | 1 | 0.84619384 | `Castro de Mariz` | Chantada |
| 6 | val | 1 | 0.84609869 | `Castro de San Bartolomeu` | A Estrada |
| 7 | val | 1 | 0.83338610 | `Castro de Outeiro/O Castro` | A Estrada |
| 8 | val | 1 | 0.82773343 | `Os Castros/Veiga dos Castros` | Foz |
| 9 | val | 1 | 0.82731069 | `Os Castros` | A Fonsagrada |
| 10 | val | 1 | 0.82128280 | `Monte dos Castros` | Foz |

## O Val Holdout

| Rank | Class | Score | Name | Reading |
|---:|---:|---:|---|---|
| 34 | 1 | 0.62403120 | `Castro da Pedreira` | known positive |
| 68 | 1 | 0.56504615 | `Monte do Castro (Castro de Vilasuso)` | known positive |
| 78 | 1 | 0.55542385 | `O Castro (Castro de Quintá)` | known positive |
| 116 | 0 | 0.50206187 | `Mámoa do Val/Mámoa de Santa Margarida` | hard negative |
| 204 | 1 | 0.02294685 | `Castro de Pena Lopesa` | known positive |

At least one known O Val positive ranks below the O Val hard negative. This is the main local warning: RGB-only ranking is useful, but it is not enough for final candidate decisions.

## Interpretation

A useful RGB baseline should rank known positives above hard negatives in `val` and should not collapse on the O Val/Trasancos holdouts. This run shows a weak but real RGB ranking signal, not a deployable detector.

The strongest caution is local: `Castro de Pena Lopesa` is missed in the O Val holdout. That means the next phase must add LiDAR/relief and visual review before any claim about candidate discovery.

The default feature radius is fixed for every chip to avoid leaking label-derived radius priors into the RGB baseline. The train set here is `train-mini`, not full train. Keep this as a cheap go/no-go check before downloading all remaining chips.
