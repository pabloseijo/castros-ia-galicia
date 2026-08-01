# Weak-label RGB+relief baseline v1

Generated: 2026-08-01T00:00:00Z

## What This Is

Minimal fusion ranker over weak labels. It joins the existing RGB handcrafted features with MDT5 relief features and morphology-aware relief variants.
It is a ranking sanity check for review prioritization, not an archaeological detector.

## Files

- RGB feature TSV: `data/weak-label-baseline-v1/weak_label_rgb_baseline_full_features.tsv`
- Relief feature TSVs: `data/weak-label-relief-v1/weak_label_relief_features_train.tsv`, `data/weak-label-relief-v1/weak_label_relief_features_val.tsv`, `data/weak-label-relief-v1/weak_label_relief_features_test.tsv`, `data/weak-label-relief-v1/weak_label_relief_features_holdouts.tsv`
- Feature table: `data/weak-label-fusion-v1/weak_label_rgb_relief_full_features.tsv`
- Score table: `data/weak-label-fusion-v1/weak_label_rgb_relief_full_scores.tsv`
- Metrics table: `data/weak-label-fusion-v1/weak_label_rgb_relief_full_metrics.tsv`
- Model weights JSON: `data/weak-label-fusion-v1/weak_label_rgb_relief_full_model.json`

## Training Setup

- Train dataset: `train`
- Feature count: 47
- Logistic epochs: 900
- Learning rate: 0.06
- L2: 0.02
- Final train loss: 0.386808
- Signal status: `rgb_relief_ranking_signal_present`

## Feature Rows

- failed: 837
- ok: 13079

## Dataset Counts

- holdouts: 204 rows (68 positives, 136 hard negatives)
- test: 2383 rows (528 positives, 1855 hard negatives)
- train: 8641 rows (1844 positives, 6797 hard negatives)
- val: 1851 rows (359 positives, 1492 hard negatives)

## Metrics

| Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| holdouts | all | 204 | 68 | 136 | 0.925281 | 0.880837 | 0.880000 | 0.647059 | 1 | 36.5 |
| holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| holdouts | split:test_trasancos | 199 | 64 | 135 | 0.935764 | 0.879315 | 0.840000 | 0.656250 | 1 | 34.5 |
| test | all | 2383 | 528 | 1855 | 0.910299 | 0.774873 | 0.940000 | 0.089015 | 1 | 312.5 |
| train | all | 8641 | 1844 | 6797 | 0.916019 | 0.793529 | 1.000000 | 0.027115 | 1 | 1057.5 |
| val | all | 1851 | 359 | 1492 | 0.905931 | 0.759620 | 0.940000 | 0.130919 | 1 | 206.0 |

## References

- RGB holdouts: ROC-AUC `0.862565`, AP `0.770981`.
- RGB val: ROC-AUC `0.709889`, AP `0.417477`.
- relief train: ROC-AUC `0.791347`, AP `0.561261`.
- relief val: ROC-AUC `0.769258`, AP `0.502154`.
- relief test: ROC-AUC `0.795613`, AP `0.586476`.
- relief holdouts: ROC-AUC `0.730536`, AP `0.636385`.

## Top Scores

### test

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test | 1 | 0.99999127 | `Castro de Vilarmeor` | Negueira de Muñiz |
| 2 | test | 1 | 0.99998892 | `Castro de Parada/A Roda do Castro` | Samos |
| 3 | test | 1 | 0.99995122 | `Castro de Toralla` | Vigo |
| 4 | test | 1 | 0.99988259 | `Castro do Teso dos Mouros` | Quiroga |
| 5 | test | 1 | 0.99981630 | `Castro de Val de Parada` | Quiroga |
| 6 | test | 1 | 0.99979813 | `Castro de Rei` | Castro de Rei |
| 7 | test | 1 | 0.99969956 | `Castro do Xardoal` | O Barco de Valdeorras |
| 8 | test | 1 | 0.99965277 | `O Castro` | Fornelos de Montes |
| 9 | test | 1 | 0.99963125 | `Os Castros de San Cristovo/Monte da Rodela` | Quiroga |
| 10 | test | 1 | 0.99959213 | `Castro da Xabrega/Cotarro do Castro` | Sober |

### holdouts

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test_trasancos | 1 | 0.99965127 | `Castro de Lobariz` | Ferrol |
| 2 | test_trasancos | 1 | 0.99320764 | `Castro de Punta Taraza` | Valdoviño |
| 3 | test_trasancos | 1 | 0.99170236 | `Castro de Vilasanche` | Ferrol |
| 4 | test_trasancos | 1 | 0.99113103 | `Necrópole de Santa Comba/Castro de Santa Comba` | Ferrol |
| 5 | test_trasancos | 1 | 0.98933221 | `A Croa do Redo` | San Sadurniño |
| 6 | test_trasancos | 1 | 0.98273265 | `Castro de Viladonelle` | Neda |
| 7 | test_trasancos | 1 | 0.98214149 | `Castro de Tralocastro` | Ferrol |
| 8 | test_trasancos | 1 | 0.97391330 | `Castro das Pías/Castro de Cardoeiro` | Fene |
| 9 | test_trasancos | 1 | 0.96214754 | `Castro da Revolta` | Narón |
| 10 | test_trasancos | 1 | 0.95964556 | `Coto da Croa` | San Sadurniño |

### val

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | val | 1 | 0.99988434 | `Medas do Castro` | O Vicedo |
| 2 | val | 1 | 0.99988357 | `O Castro Vello` | A Fonsagrada |
| 3 | val | 1 | 0.99981611 | `Castro de Cela` | Cervantes |
| 4 | val | 1 | 0.99978213 | `O Castro` | A Fonsagrada |
| 5 | val | 1 | 0.99977005 | `Castro da Castañosa` | A Fonsagrada |
| 6 | val | 1 | 0.99975900 | `Castro da Ribada` | Chantada |
| 7 | val | 1 | 0.99967646 | `Castro de Corneantes` | Cervantes |
| 8 | val | 1 | 0.99949062 | `Castro de Estaca de Bares` | Mañón |
| 9 | val | 1 | 0.99933566 | `Castro de Marful` | A Fonsagrada |
| 10 | val | 1 | 0.99926389 | `Castro de Santa Catalina/Pena Tallada` | Cervantes |

## O Val Reading

- rank `16`: `O Castro (Castro de Quintá)` (positive), score `0.93484924`.
- rank `17`: `Castro da Pedreira` (positive), score `0.92970190`.
- rank `33`: `Monte do Castro (Castro de Vilasuso)` (positive), score `0.78639438`.
- rank `114`: `Mámoa do Val/Mámoa de Santa Margarida` (hard_negative), score `0.13950332`.
- rank `201`: `Castro de Pena Lopesa` (positive), score `0.01961880`.

## Interpretation

Fusion should improve `val` without collapsing the spatial holdouts. If it only improves the tiny O Val subset, treat it as overfit/error-analysis evidence.
The current labels are weak and negatives are not guaranteed true absences, so this model is for prioritization and ablation, not discovery claims.
