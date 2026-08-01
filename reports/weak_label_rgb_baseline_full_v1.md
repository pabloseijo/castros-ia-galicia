# Weak-label RGB baseline v1

Generated: 2026-08-01T00:00:00Z

## What This Is

Minimal RGB chip classifier/ranker over weak labels. It uses handcrafted color/edge/ring features and a small logistic regression implemented with numpy.
It is a modelling sanity check, not an archaeological detector.

## Files

- Train manifest: `data/weak-label-splits-v1/weak_label_chip_export_train.tsv`
- Eval manifests: `data/weak-label-splits-v1/weak_label_chip_export_val.tsv`, `data/weak-label-splits-v1/weak_label_chip_export_test.tsv`, `data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv`
- Feature table: `data/weak-label-baseline-v1/weak_label_rgb_baseline_full_features.tsv`
- Score table: `data/weak-label-baseline-v1/weak_label_rgb_baseline_full_scores.tsv`
- Metrics table: `data/weak-label-baseline-v1/weak_label_rgb_baseline_full_metrics.tsv`
- Model weights JSON: `data/weak-label-baseline-v1/weak_label_rgb_baseline_full_model.json`

## Training Setup

- Feature image size: 192x192px
- Radius mode: `fixed`
- Fixed feature radius: 120.0 m
- Logistic epochs: 900
- Learning rate: 0.06
- L2: 0.01
- Final train loss: 0.612841
- Signal status: `weak_rgb_ranking_signal_present`

## Feature Extraction

- ok: 13916

## Dataset Counts

- holdouts: 204 rows (68 positives, 136 hard negatives)
- test: 2530 rows (564 positives, 1966 hard negatives)
- train: 9145 rows (2014 positives, 7131 hard negatives)
- val: 2037 rows (425 positives, 1612 hard negatives)

## Metrics

| Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| holdouts | all | 204 | 68 | 136 | 0.862565 | 0.770981 | 0.820000 | 0.602941 | 1 | 39.5 |
| holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| holdouts | split:test_trasancos | 199 | 64 | 135 | 0.872338 | 0.769360 | 0.800000 | 0.625000 | 1 | 37.5 |
| holdouts | source:ign_pnoa_rgb | 204 | 68 | 136 | 0.862565 | 0.770981 | 0.820000 | 0.602941 | 1 | 39.5 |
| test | all | 2530 | 564 | 1966 | 0.743694 | 0.482859 | 0.700000 | 0.062057 | 2 | 584.0 |
| test | source:dgt_ortos2021_rgb | 147 | 36 | 111 | 0.521021 | 0.286604 | 0.280000 | 0.388889 | 2 | 78.5 |
| test | source:ign_pnoa_rgb | 2383 | 528 | 1855 | 0.767334 | 0.497648 | 0.700000 | 0.066288 | 2 | 519.5 |
| train | all | 9145 | 2014 | 7131 | 0.730968 | 0.491341 | 0.900000 | 0.022344 | 1 | 2124.0 |
| train | source:dgt_ortos2021_rgb | 504 | 170 | 334 | 0.564248 | 0.355670 | 0.220000 | 0.064706 | 1 | 218.5 |
| train | source:ign_pnoa_rgb | 8641 | 1844 | 6797 | 0.758435 | 0.513146 | 0.900000 | 0.024403 | 1 | 1807.0 |
| val | all | 2037 | 425 | 1612 | 0.709889 | 0.417477 | 0.660000 | 0.077647 | 1 | 550.0 |
| val | source:dgt_ortos2021_rgb | 186 | 66 | 120 | 0.562374 | 0.387863 | 0.380000 | 0.287879 | 1 | 84.0 |
| val | source:ign_pnoa_rgb | 1851 | 359 | 1492 | 0.756297 | 0.441023 | 0.660000 | 0.091922 | 1 | 439.0 |

## Top Holdout Scores

### test

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test | 0 | 0.94488579 | `Picacho/San Francisco` | Vigo |
| 2 | test | 1 | 0.94464419 | `Castro Castriño de Coia` | Vigo |
| 3 | test | 1 | 0.92997412 | `Castro de Todón` | Becerreá |
| 4 | test | 0 | 0.92622871 | `Sartego da Ladeira` | Vigo |
| 5 | test | 1 | 0.92316583 | `Castro de Lourido` | Samos |
| 6 | test | 0 | 0.92179745 | `Sartego de San Roque` | Vigo |
| 7 | test | 1 | 0.91980742 | `Castro do Sino` | Vigo |
| 8 | test | 1 | 0.91594330 | `Castro das Varelas` | Melide |
| 9 | test | 1 | 0.91121148 | `O Castro` | Palas de Rei |
| 10 | test | 0 | 0.90827566 | `Sartego de Coia` | Vigo |

### holdouts

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test_trasancos | 1 | 0.92163692 | `Castro de Ferrol Vello` | Ferrol |
| 2 | test_trasancos | 1 | 0.90330209 | `Porta do Castro/Arco do Cristo` | Ferrol |
| 3 | test_trasancos | 0 | 0.84917936 | `Mámoa do Rego da Moa` | Fene |
| 4 | test_trasancos | 0 | 0.84278876 | `Mámoa de Rioboo 1/Mámoa de Canteiros 1` | Valdoviño |
| 5 | test_trasancos | 1 | 0.80291252 | `Castro das Pías/Castro de Cardoeiro` | Fene |
| 6 | test_trasancos | 1 | 0.78937823 | `Castro de Canido` | Ferrol |
| 7 | test_trasancos | 1 | 0.78630690 | `O Castro` | Narón |
| 8 | test_trasancos | 1 | 0.76601432 | `Castro de Santa Mariña/Os Castros Altos` | Ferrol |
| 9 | test_trasancos | 1 | 0.76569946 | `Castro da Revolta` | Narón |
| 10 | test_o_val | 1 | 0.75753255 | `O Castro (Castro de Quintá)` | Narón |

### val

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | val | 1 | 0.93626658 | `Castro de Xaz/Castro de Abeleiras/Os Redondos` | Oleiros |
| 2 | val | 1 | 0.87770399 | `Castro de Vilagude/Chan do Castro` | A Estrada |
| 3 | val | 1 | 0.87604711 | `Castro da Pobra de Parga` | Guitiriz |
| 4 | val | 1 | 0.87514742 | `Os Castros` | Chantada |
| 5 | val | 1 | 0.87347084 | `Castro de Mariz` | Chantada |
| 6 | val | 1 | 0.87034778 | `Castro de Airoá` | Chantada |
| 7 | val | 1 | 0.86232206 | `Castro da Croa` | Riotorto |
| 8 | val | 0 | 0.85761492 | `O Castelo` | O Vicedo |
| 9 | val | 1 | 0.85584055 | `As Cercas/O Castro/Eira dos Mouros` | A Estrada |
| 10 | val | 1 | 0.84812526 | `O Castro` | A Estrada |

## O Val Holdout

| Rank | Class | Score | Name | Reading |
|---:|---:|---:|---|---|
| 10 | 1 | 0.75753255 | `O Castro (Castro de Quintá)` | known positive |
| 48 | 1 | 0.57787673 | `Castro da Pedreira` | known positive |
| 56 | 1 | 0.55655683 | `Monte do Castro (Castro de Vilasuso)` | known positive |
| 74 | 0 | 0.44924408 | `Mámoa do Val/Mámoa de Santa Margarida` | hard negative |
| 204 | 1 | 0.01452281 | `Castro de Pena Lopesa` | known positive |

At least one known O Val positive ranks below the O Val hard negative. This is the main local warning: RGB-only ranking is useful, but it is not enough for final candidate decisions.

## Interpretation

A useful RGB baseline should rank known positives above hard negatives in `val` and should not collapse on the O Val/Trasancos holdouts. This run shows a weak but real RGB ranking signal, not a deployable detector.

The strongest caution is local: `Castro de Pena Lopesa` is missed in the O Val holdout. That means the next phase must add LiDAR/relief and visual review before any claim about candidate discovery.

The default feature radius is fixed for every chip to avoid leaking label-derived radius priors into the RGB baseline. The train set here is the full `train` chip export. Treat this as the RGB sanity baseline before relief fusion, error review, and any candidate-discovery claim.
