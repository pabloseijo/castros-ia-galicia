# Weak-label relief baseline test

Generated: 2026-08-01T00:00:00Z

## What This Is

A first relief/MDT ranking baseline over `test`. It uses public MDT5 WCS crops, derives slope, hillshade and local relief in memory, then scores topographic/radial contrast.
It is a ranking sanity check, not an archaeological detector.

## Files

- Relief manifest: `data/weak-label-relief-v1/weak_label_relief_wcs_test.tsv`
- Feature TSV: `data/weak-label-relief-v1/weak_label_relief_features_test.tsv`
- Score TSV: `data/weak-label-relief-v1/weak_label_relief_scores_test.tsv`
- Metrics TSV: `data/weak-label-relief-v1/weak_label_relief_metrics_test.tsv`

## Setup

- Fixed feature radius: 120.0 m
- LRM radius: 50.0 m
- Signal status: `weak_relief_ranking_signal_present`

## Feature Extraction

- failed: 147
- ok: 2383

## Metrics

| Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 2383 | 528 | 1855 | 0.795613 | 0.586476 | 0.820000 | 0.077652 | 1 | 430.0 |
| split:test | 2383 | 528 | 1855 | 0.795613 | 0.586476 | 0.820000 | 0.077652 | 1 | 430.0 |

## RGB Baseline Reference

- RGB all: ROC-AUC `0.862565`, AP `0.770981`.
- RGB split:test_o_val: ROC-AUC `0.750000`, AP `0.950000`.
- RGB split:test_trasancos: ROC-AUC `0.872338`, AP `0.769360`.

## Top Relief Scores

### all

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test | 1 | 12.66820534 | `Castro de Toralla` | Vigo |
| 2 | test | 1 | 5.24933426 | `Castro de Rei` | Castro de Rei |
| 3 | test | 1 | 4.74308646 | `Castro de Ruela/Os Castros de Rueta` | Cervo |
| 4 | test | 1 | 4.53853114 | `Castro de Pazos` | O Valadouro |
| 5 | test | 1 | 4.44856043 | `Castro de Porto Nadelas/Castro Nadelas` | Porto do Son |
| 6 | test | 1 | 4.29321812 | `Castro de Melide/Castelo` | Melide |
| 7 | test | 1 | 4.19379118 | `A Croa do castro/Castro Lampreeiro` | Noia |
| 8 | test | 0 | 4.03683213 | `Castelo Pequeno` | Monforte de Lemos |
| 9 | test | 1 | 3.93067751 | `Xacemento da península da Atalaia` | Cervo |
| 10 | test | 1 | 3.85019163 | `Castro de Vilarmeor` | Negueira de Muñiz |

### test

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test | 1 | 12.66820534 | `Castro de Toralla` | Vigo |
| 2 | test | 1 | 5.24933426 | `Castro de Rei` | Castro de Rei |
| 3 | test | 1 | 4.74308646 | `Castro de Ruela/Os Castros de Rueta` | Cervo |
| 4 | test | 1 | 4.53853114 | `Castro de Pazos` | O Valadouro |
| 5 | test | 1 | 4.44856043 | `Castro de Porto Nadelas/Castro Nadelas` | Porto do Son |
| 6 | test | 1 | 4.29321812 | `Castro de Melide/Castelo` | Melide |
| 7 | test | 1 | 4.19379118 | `A Croa do castro/Castro Lampreeiro` | Noia |
| 8 | test | 0 | 4.03683213 | `Castelo Pequeno` | Monforte de Lemos |
| 9 | test | 1 | 3.93067751 | `Xacemento da península da Atalaia` | Cervo |
| 10 | test | 1 | 3.85019163 | `Castro de Vilarmeor` | Negueira de Muñiz |


## Interpretation

Relief/MDT5 can detect broad topographic and radial contrast, but its 5 m grid is still coarse for buried walls or ditches. Treat this as a prioritization layer. Fine LiDAR/LAZ or richer derived products are still needed before candidate claims.
