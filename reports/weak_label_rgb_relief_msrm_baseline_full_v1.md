# Weak-label RGB+relief baseline v1

Generated: 2026-08-01T00:00:00Z

## What This Is

Minimal fusion ranker over weak labels. It joins the existing RGB handcrafted features with MDT5 relief features and morphology-aware relief variants.
It is a ranking sanity check for review prioritization, not an archaeological detector.

## Files

- RGB feature TSV: `data/weak-label-baseline-v1/weak_label_rgb_baseline_full_features.tsv`
- Relief feature TSVs: `data/weak-label-relief-v1/weak_label_relief_features_train.tsv`, `data/weak-label-relief-v1/weak_label_relief_features_val.tsv`, `data/weak-label-relief-v1/weak_label_relief_features_test.tsv`, `data/weak-label-relief-v1/weak_label_relief_features_holdouts.tsv`
- Feature table: `data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_features.tsv`
- Score table: `data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_scores.tsv`
- Metrics table: `data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_metrics.tsv`
- Model weights JSON: `data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_model.json`

## Training Setup

- Train dataset: `train`
- Feature count: 60
- Logistic epochs: 900
- Learning rate: 0.06
- L2: 0.02
- Final train loss: 0.346625
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
| holdouts | all | 204 | 68 | 136 | 0.944312 | 0.909383 | 0.900000 | 0.661765 | 1 | 35.5 |
| holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| holdouts | split:test_trasancos | 199 | 64 | 135 | 0.947917 | 0.907557 | 0.880000 | 0.687500 | 1 | 33.5 |
| test | all | 2383 | 528 | 1855 | 0.925436 | 0.812968 | 1.000000 | 0.094697 | 1 | 302.5 |
| train | all | 8641 | 1844 | 6797 | 0.932440 | 0.829662 | 1.000000 | 0.027115 | 1 | 1036.5 |
| val | all | 1851 | 359 | 1492 | 0.927349 | 0.799049 | 0.960000 | 0.133705 | 1 | 200.0 |

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
| 1 | test | 1 | 0.99995241 | `Castro de Toralla` | Vigo |
| 2 | test | 1 | 0.99993014 | `Castro de Parada/A Roda do Castro` | Samos |
| 3 | test | 1 | 0.99985477 | `Castro de Vilarmeor` | Negueira de Muñiz |
| 4 | test | 1 | 0.99985194 | `Castro de Rei` | Castro de Rei |
| 5 | test | 1 | 0.99964669 | `Castro do Sino` | Vigo |
| 6 | test | 1 | 0.99942423 | `Os Castros de San Cristovo/Monte da Rodela` | Quiroga |
| 7 | test | 1 | 0.99942040 | `Castro de Val de Parada` | Quiroga |
| 8 | test | 1 | 0.99923417 | `O Castro` | Fornelos de Montes |
| 9 | test | 1 | 0.99910173 | `Castro da Pena da Coucada` | Quiroga |
| 10 | test | 1 | 0.99896166 | `Os Castros` | Becerreá |

### holdouts

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test_trasancos | 1 | 0.99962491 | `Castro de Lobariz` | Ferrol |
| 2 | test_trasancos | 1 | 0.99434845 | `Necrópole de Santa Comba/Castro de Santa Comba` | Ferrol |
| 3 | test_trasancos | 1 | 0.99395697 | `A Croa do Redo` | San Sadurniño |
| 4 | test_o_val | 1 | 0.99291529 | `O Castro (Castro de Quintá)` | Narón |
| 5 | test_trasancos | 1 | 0.98951045 | `Castro de Vilasanche` | Ferrol |
| 6 | test_trasancos | 1 | 0.98773734 | `Castro de Tralocastro` | Ferrol |
| 7 | test_trasancos | 1 | 0.98422959 | `Castro da Revolta` | Narón |
| 8 | test_trasancos | 1 | 0.98361153 | `Castro de Punta Taraza` | Valdoviño |
| 9 | test_trasancos | 1 | 0.98186596 | `A Croa do Castro` | San Sadurniño |
| 10 | test_trasancos | 1 | 0.97785644 | `Castro` | Valdoviño |

### val

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | val | 1 | 0.99972487 | `Castro de Corneantes` | Cervantes |
| 2 | val | 1 | 0.99963893 | `O Castro Vello` | A Fonsagrada |
| 3 | val | 1 | 0.99963858 | `O Castro` | A Fonsagrada |
| 4 | val | 1 | 0.99961456 | `Castro da Castañosa` | A Fonsagrada |
| 5 | val | 1 | 0.99952853 | `Castro da Ribada` | Chantada |
| 6 | val | 1 | 0.99940462 | `Medas do Castro` | O Vicedo |
| 7 | val | 1 | 0.99927430 | `Chao do Castro` | A Fonsagrada |
| 8 | val | 1 | 0.99927160 | `Castro de Cela` | Cervantes |
| 9 | val | 1 | 0.99883684 | `Castro de Estaca de Bares` | Mañón |
| 10 | val | 1 | 0.99869345 | `O Castro` | A Fonsagrada |

## O Val Reading

- rank `4`: `O Castro (Castro de Quintá)` (positive), score `0.99291529`.
- rank `16`: `Monte do Castro (Castro de Vilasuso)` (positive), score `0.95201300`.
- rank `24`: `Castro da Pedreira` (positive), score `0.91701271`.
- rank `110`: `Mámoa do Val/Mámoa de Santa Margarida` (hard_negative), score `0.14298555`.
- rank `131`: `Castro de Pena Lopesa` (positive), score `0.07690272`.

## Interpretation

Fusion should improve `val` without collapsing the spatial holdouts. If it only improves the tiny O Val subset, treat it as overfit/error-analysis evidence.
The current labels are weak and negatives are not guaranteed true absences, so this model is for prioritization and ablation, not discovery claims.
