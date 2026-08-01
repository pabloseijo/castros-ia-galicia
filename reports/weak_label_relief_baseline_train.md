# Weak-label relief baseline train

Generated: 2026-08-01T00:00:00Z

## What This Is

A first relief/MDT ranking baseline over `train`. It uses public MDT5 WCS crops, derives slope, hillshade and local relief in memory, then scores topographic/radial contrast.
It is a ranking sanity check, not an archaeological detector.

## Files

- Relief manifest: `data/weak-label-relief-v1/weak_label_relief_wcs_train.tsv`
- Feature TSV: `data/weak-label-relief-v1/weak_label_relief_features_train.tsv`
- Score TSV: `data/weak-label-relief-v1/weak_label_relief_scores_train.tsv`
- Metrics TSV: `data/weak-label-relief-v1/weak_label_relief_metrics_train.tsv`

## Setup

- Fixed feature radius: 120.0 m
- LRM radius: 50.0 m
- Signal status: `weak_relief_ranking_signal_present`

## Feature Extraction

- failed: 504
- ok: 8641

## Metrics

| Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 8641 | 1844 | 6797 | 0.791347 | 0.561261 | 0.880000 | 0.023861 | 1 | 1640.0 |
| split:train | 8641 | 1844 | 6797 | 0.791347 | 0.561261 | 0.880000 | 0.023861 | 1 | 1640.0 |

## RGB Baseline Reference

- RGB all: ROC-AUC `0.862565`, AP `0.770981`.
- RGB split:test_o_val: ROC-AUC `0.750000`, AP `0.950000`.
- RGB split:test_trasancos: ROC-AUC `0.872338`, AP `0.769360`.

## Top Relief Scores

### all

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | train | 1 | 9.73828569 | `Castro dos Fornos/Punta de Frades` | Cariño |
| 2 | train | 1 | 7.14306249 | `Campo do Castro` | Cedeira |
| 3 | train | 1 | 6.35836788 | `Castro de Marce` | Pantón |
| 4 | train | 0 | 5.86196709 | `Mámoa da Pedra dos Mouros 4` | Vimianzo |
| 5 | train | 0 | 5.62442080 | `Petróglifo de Meira` | Moaña |
| 6 | train | 1 | 5.41517130 | `Castro de Santa Marta` | Baiona |
| 7 | train | 1 | 5.40993365 | `Castro de Punta Sardiñeiro` | Fisterra |
| 8 | train | 1 | 5.34155753 | `Castro do Galiñeiro` | Gondomar |
| 9 | train | 1 | 5.27549563 | `A Volta dos Castros` | Ortigueira |
| 10 | train | 1 | 5.23211317 | `Castro de Gastrar` | Boqueixón |

### train

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | train | 1 | 9.73828569 | `Castro dos Fornos/Punta de Frades` | Cariño |
| 2 | train | 1 | 7.14306249 | `Campo do Castro` | Cedeira |
| 3 | train | 1 | 6.35836788 | `Castro de Marce` | Pantón |
| 4 | train | 0 | 5.86196709 | `Mámoa da Pedra dos Mouros 4` | Vimianzo |
| 5 | train | 0 | 5.62442080 | `Petróglifo de Meira` | Moaña |
| 6 | train | 1 | 5.41517130 | `Castro de Santa Marta` | Baiona |
| 7 | train | 1 | 5.40993365 | `Castro de Punta Sardiñeiro` | Fisterra |
| 8 | train | 1 | 5.34155753 | `Castro do Galiñeiro` | Gondomar |
| 9 | train | 1 | 5.27549563 | `A Volta dos Castros` | Ortigueira |
| 10 | train | 1 | 5.23211317 | `Castro de Gastrar` | Boqueixón |


## Interpretation

Relief/MDT5 can detect broad topographic and radial contrast, but its 5 m grid is still coarse for buried walls or ditches. Treat this as a prioritization layer. Fine LiDAR/LAZ or richer derived products are still needed before candidate claims.
