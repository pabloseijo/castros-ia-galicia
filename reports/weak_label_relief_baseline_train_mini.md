# Weak-label relief baseline train_mini

Generated: 2026-08-01T00:00:00Z

## What This Is

A first relief/MDT ranking baseline over `train_mini`. It uses public MDT5 WCS crops, derives slope, hillshade and local relief in memory, then scores topographic/radial contrast.
It is a ranking sanity check, not an archaeological detector.

## Files

- Relief manifest: `data/weak-label-relief-v1/weak_label_relief_wcs_train_mini.tsv`
- Feature TSV: `data/weak-label-relief-v1/weak_label_relief_features_train_mini.tsv`
- Score TSV: `data/weak-label-relief-v1/weak_label_relief_scores_train_mini.tsv`
- Metrics TSV: `data/weak-label-relief-v1/weak_label_relief_metrics_train_mini.tsv`

## Setup

- Fixed feature radius: 120.0 m
- LRM radius: 50.0 m
- Signal status: `weak_relief_ranking_signal_present`

## Feature Extraction

- failed: 447
- ok: 553

## Metrics

| Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 553 | 276 | 277 | 0.747449 | 0.735998 | 0.820000 | 0.148551 | 1 | 185.5 |
| split:train | 553 | 276 | 277 | 0.747449 | 0.735998 | 0.820000 | 0.148551 | 1 | 185.5 |

## RGB Baseline Reference

- RGB all: ROC-AUC `0.710748`, AP `0.633197`.
- RGB split:test_o_val: ROC-AUC `0.750000`, AP `0.950000`.
- RGB split:test_trasancos: ROC-AUC `0.715741`, AP `0.631740`.

## Top Relief Scores

### all

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | train | 1 | 5.85332251 | `Campo do Castro` | Cedeira |
| 2 | train | 1 | 4.34267862 | `A Volta dos Castros` | Ortigueira |
| 3 | train | 1 | 3.27561922 | `Castro Pereiro` | Trazo |
| 4 | train | 0 | 2.97689254 | `Castelo` | Mondoñedo |
| 5 | train | 1 | 2.85096407 | `A Roda do Castro` | Ares |
| 6 | train | 1 | 2.84330938 | `Castro da Barda` | Ponteceso |
| 7 | train | 1 | 2.65429101 | `Castro da Lama` | A Lama |
| 8 | train | 1 | 2.65324441 | `Castro da Illa da Estrela` | Ponteceso |
| 9 | train | 1 | 2.34911193 | `Castrillón/Castro de Santa Eirena` | Carballo |
| 10 | train | 1 | 2.31370019 | `A Torre do Castelo/O Castro` | Outes |

### train

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | train | 1 | 5.85332251 | `Campo do Castro` | Cedeira |
| 2 | train | 1 | 4.34267862 | `A Volta dos Castros` | Ortigueira |
| 3 | train | 1 | 3.27561922 | `Castro Pereiro` | Trazo |
| 4 | train | 0 | 2.97689254 | `Castelo` | Mondoñedo |
| 5 | train | 1 | 2.85096407 | `A Roda do Castro` | Ares |
| 6 | train | 1 | 2.84330938 | `Castro da Barda` | Ponteceso |
| 7 | train | 1 | 2.65429101 | `Castro da Lama` | A Lama |
| 8 | train | 1 | 2.65324441 | `Castro da Illa da Estrela` | Ponteceso |
| 9 | train | 1 | 2.34911193 | `Castrillón/Castro de Santa Eirena` | Carballo |
| 10 | train | 1 | 2.31370019 | `A Torre do Castelo/O Castro` | Outes |


## Interpretation

Relief/MDT5 can detect broad topographic and radial contrast, but its 5 m grid is still coarse for buried walls or ditches. Treat this as a prioritization layer. Fine LiDAR/LAZ or richer derived products are still needed before candidate claims.
