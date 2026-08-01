# Weak-label relief baseline val

Generated: 2026-08-01T00:00:00Z

## What This Is

A first relief/MDT ranking baseline over `val`. It uses public MDT5 WCS crops, derives slope, hillshade and local relief in memory, then scores topographic/radial contrast.
It is a ranking sanity check, not an archaeological detector.

## Files

- Relief manifest: `data/weak-label-relief-v1/weak_label_relief_wcs_val.tsv`
- Feature TSV: `data/weak-label-relief-v1/weak_label_relief_features_val.tsv`
- Score TSV: `data/weak-label-relief-v1/weak_label_relief_scores_val.tsv`
- Metrics TSV: `data/weak-label-relief-v1/weak_label_relief_metrics_val.tsv`

## Setup

- Fixed feature radius: 120.0 m
- LRM radius: 50.0 m
- Signal status: `weak_relief_ranking_signal_present`

## Feature Extraction

- failed: 186
- ok: 1851

## Metrics

| Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 1851 | 359 | 1492 | 0.769258 | 0.502154 | 0.780000 | 0.108635 | 1 | 340.0 |
| split:val | 1851 | 359 | 1492 | 0.769258 | 0.502154 | 0.780000 | 0.108635 | 1 | 340.0 |

## RGB Baseline Reference

- RGB all: ROC-AUC `0.710748`, AP `0.633197`.
- RGB split:test_o_val: ROC-AUC `0.750000`, AP `0.950000`.
- RGB split:test_trasancos: ROC-AUC `0.715741`, AP `0.631740`.

## Top Relief Scores

### all

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | val | 1 | 5.15030608 | `Medas do Castro` | O Vicedo |
| 2 | val | 1 | 4.80963042 | `Castro de Estaca de Bares` | Mañón |
| 3 | val | 1 | 4.43334500 | `Punta dos Castros` | Foz |
| 4 | val | 1 | 4.38546531 | `Castro da Insua` | O Vicedo |
| 5 | val | 0 | 3.96204768 | `Mámoa de Guidoiro Areoso 2` | A Illa de Arousa |
| 6 | val | 1 | 3.86160566 | `Castro de San Bartolo` | Barreiros |
| 7 | val | 1 | 3.67769824 | `Castro de Vilagude/Chan do Castro` | A Estrada |
| 8 | val | 1 | 3.29414679 | `Castro da Cabeza` | Viana do Bolo |
| 9 | val | 1 | 3.05607269 | `O Castro` | A Estrada |
| 10 | val | 0 | 2.97080695 | `Mámoa de Guidoiro Areoso 3` | A Illa de Arousa |

### val

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | val | 1 | 5.15030608 | `Medas do Castro` | O Vicedo |
| 2 | val | 1 | 4.80963042 | `Castro de Estaca de Bares` | Mañón |
| 3 | val | 1 | 4.43334500 | `Punta dos Castros` | Foz |
| 4 | val | 1 | 4.38546531 | `Castro da Insua` | O Vicedo |
| 5 | val | 0 | 3.96204768 | `Mámoa de Guidoiro Areoso 2` | A Illa de Arousa |
| 6 | val | 1 | 3.86160566 | `Castro de San Bartolo` | Barreiros |
| 7 | val | 1 | 3.67769824 | `Castro de Vilagude/Chan do Castro` | A Estrada |
| 8 | val | 1 | 3.29414679 | `Castro da Cabeza` | Viana do Bolo |
| 9 | val | 1 | 3.05607269 | `O Castro` | A Estrada |
| 10 | val | 0 | 2.97080695 | `Mámoa de Guidoiro Areoso 3` | A Illa de Arousa |


## Interpretation

Relief/MDT5 can detect broad topographic and radial contrast, but its 5 m grid is still coarse for buried walls or ditches. Treat this as a prioritization layer. Fine LiDAR/LAZ or richer derived products are still needed before candidate claims.
