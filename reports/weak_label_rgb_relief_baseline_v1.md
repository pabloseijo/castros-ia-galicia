# Weak-label RGB+relief baseline v1

Generated: 2026-08-01T00:00:00Z

## What This Is

Minimal fusion ranker over weak labels. It joins the existing RGB handcrafted features with MDT5 relief features and morphology-aware relief variants.
It is a ranking sanity check for review prioritization, not an archaeological detector.

## Files

- RGB feature TSV: `data/weak-label-baseline-v1/weak_label_rgb_baseline_features.tsv`
- Relief feature TSVs: `data/weak-label-relief-v1/weak_label_relief_features_train_mini.tsv`, `data/weak-label-relief-v1/weak_label_relief_features_val.tsv`, `data/weak-label-relief-v1/weak_label_relief_features_holdouts.tsv`
- Feature table: `data/weak-label-fusion-v1/weak_label_rgb_relief_features.tsv`
- Score table: `data/weak-label-fusion-v1/weak_label_rgb_relief_scores.tsv`
- Metrics table: `data/weak-label-fusion-v1/weak_label_rgb_relief_metrics.tsv`
- Model weights JSON: `data/weak-label-fusion-v1/weak_label_rgb_relief_model.json`

## Training Setup

- Train dataset: `train_mini`
- Feature count: 47
- Logistic epochs: 900
- Learning rate: 0.06
- L2: 0.02
- Final train loss: 0.480341
- Signal status: `rgb_relief_ranking_signal_present`

## Feature Rows

- failed: 633
- ok: 2608

## Dataset Counts

- holdouts: 204 rows (68 positives, 136 hard negatives)
- train_mini: 553 rows (276 positives, 277 hard negatives)
- val: 1851 rows (359 positives, 1492 hard negatives)

## Metrics

| Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| holdouts | all | 204 | 68 | 136 | 0.888949 | 0.866398 | 0.900000 | 0.661765 | 1 | 37.5 |
| holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| holdouts | split:test_trasancos | 199 | 64 | 135 | 0.897569 | 0.864284 | 0.880000 | 0.687500 | 1 | 36.5 |
| train_mini | all | 553 | 276 | 277 | 0.869330 | 0.859469 | 0.920000 | 0.166667 | 1 | 156.5 |
| val | all | 1851 | 359 | 1492 | 0.878253 | 0.754336 | 0.980000 | 0.136490 | 1 | 207.0 |

## References

- RGB holdouts: ROC-AUC `0.710748`, AP `0.633197`.
- RGB train_mini: ROC-AUC `0.683160`, AP `0.623365`.
- RGB val: ROC-AUC `0.681073`, AP `0.381901`.
- relief train_mini: ROC-AUC `0.747449`, AP `0.735998`.
- relief val: ROC-AUC `0.769258`, AP `0.502154`.
- relief holdouts: ROC-AUC `0.730536`, AP `0.636385`.

## Top Scores

### holdouts

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test_trasancos | 1 | 0.99791519 | `Castro de Lobariz` | Ferrol |
| 2 | test_trasancos | 1 | 0.97400317 | `Castro de Vilasanche` | Ferrol |
| 3 | test_trasancos | 1 | 0.97212417 | `Necrópole de Santa Comba/Castro de Santa Comba` | Ferrol |
| 4 | test_trasancos | 1 | 0.96686012 | `Castro de Punta Taraza` | Valdoviño |
| 5 | test_trasancos | 1 | 0.93746364 | `Castro das Pías/Castro de Cardoeiro` | Fene |
| 6 | test_trasancos | 1 | 0.93632906 | `Castro da Revolta` | Narón |
| 7 | test_trasancos | 1 | 0.93602800 | `Castro de Punta Frouxeira` | Valdoviño |
| 8 | test_trasancos | 1 | 0.93335102 | `A Croa do Redo` | San Sadurniño |
| 9 | test_trasancos | 1 | 0.92144921 | `Castro de Tralocastro` | Ferrol |
| 10 | test_trasancos | 1 | 0.89929620 | `Castro de Viladonelle` | Neda |

### val

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | val | 1 | 0.99758112 | `Medas do Castro` | O Vicedo |
| 2 | val | 1 | 0.99525416 | `O Castro` | A Fonsagrada |
| 3 | val | 1 | 0.99499535 | `Castro de Estaca de Bares` | Mañón |
| 4 | val | 1 | 0.99368992 | `Castro da Ribada` | Chantada |
| 5 | val | 1 | 0.99323037 | `Castro de Couso` | A Estrada |
| 6 | val | 1 | 0.99091668 | `O Castro Vello` | A Fonsagrada |
| 7 | val | 1 | 0.98977598 | `Castro de Cela` | Cervantes |
| 8 | val | 1 | 0.98851136 | `O Castro` | A Estrada |
| 9 | val | 1 | 0.98567570 | `O Castro` | A Fonsagrada |
| 10 | val | 1 | 0.98529183 | `Punta dos Castros` | Foz |

## O Val Reading

- rank `14`: `O Castro (Castro de Quintá)` (positive), score `0.87463272`.
- rank `26`: `Castro da Pedreira` (positive), score `0.73214328`.
- rank `32`: `Monte do Castro (Castro de Vilasuso)` (positive), score `0.64752202`.
- rank `80`: `Mámoa do Val/Mámoa de Santa Margarida` (hard_negative), score `0.32277415`.
- rank `199`: `Castro de Pena Lopesa` (positive), score `0.06230073`.

## Interpretation

Fusion should improve `val` without collapsing the spatial holdouts. If it only improves the tiny O Val subset, treat it as overfit/error-analysis evidence.
The current labels are weak and negatives are not guaranteed true absences, so this model is for prioritization and ablation, not discovery claims.
