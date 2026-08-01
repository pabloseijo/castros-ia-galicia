# Weak-label relief baseline holdouts

Generated: 2026-08-01T00:00:00Z

## What This Is

A first relief/MDT ranking baseline over `holdouts`. It uses public MDT5 WCS crops, derives slope, hillshade and local relief in memory, then scores topographic/radial contrast.
It is a ranking sanity check, not an archaeological detector.

## Files

- Relief manifest: `data/weak-label-relief-v1/weak_label_relief_wcs_holdouts.tsv`
- Feature TSV: `data/weak-label-relief-v1/weak_label_relief_features_holdouts.tsv`
- Score TSV: `data/weak-label-relief-v1/weak_label_relief_scores_holdouts.tsv`
- Metrics TSV: `data/weak-label-relief-v1/weak_label_relief_metrics_holdouts.tsv`

## Setup

- Fixed feature radius: 120.0 m
- LRM radius: 50.0 m
- Signal status: `weak_relief_ranking_signal_present`

## Feature Extraction

- ok: 204

## Metrics

| Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 204 | 68 | 136 | 0.730536 | 0.636385 | 0.580000 | 0.426471 | 1 | 61.5 |
| split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| split:test_trasancos | 199 | 64 | 135 | 0.732523 | 0.627894 | 0.580000 | 0.453125 | 1 | 59.5 |

## RGB Baseline Reference

- RGB all: ROC-AUC `0.710748`, AP `0.633197`.
- RGB split:test_o_val: ROC-AUC `0.750000`, AP `0.950000`.
- RGB split:test_trasancos: ROC-AUC `0.715741`, AP `0.631740`.

## Top Relief Scores

### all

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test_trasancos | 1 | 6.53049690 | `Castro de Lobariz` | Ferrol |
| 2 | test_trasancos | 1 | 4.51217092 | `Necrópole de Santa Comba/Castro de Santa Comba` | Ferrol |
| 3 | test_trasancos | 1 | 3.61180386 | `Castro de Punta Taraza` | Valdoviño |
| 4 | test_trasancos | 1 | 2.57913878 | `Castro de Punta Frouxeira` | Valdoviño |
| 5 | test_trasancos | 1 | 2.57171448 | `Castros` | Neda |
| 6 | test_trasancos | 1 | 2.47618298 | `Castro de Vilasanche` | Ferrol |
| 7 | test_trasancos | 1 | 2.09125413 | `Castro de Viladonelle` | Neda |
| 8 | test_trasancos | 1 | 2.08607588 | `Castro das Pías/Castro de Cardoeiro` | Fene |
| 9 | test_trasancos | 1 | 1.94308726 | `Castro Das Croas` | San Sadurniño |
| 10 | test_o_val | 1 | 1.88998989 | `O Castro (Castro de Quintá)` | Narón |

### test_o_val

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 10 | test_o_val | 1 | 1.88998989 | `O Castro (Castro de Quintá)` | Narón |
| 59 | test_o_val | 1 | 0.45731483 | `Castro da Pedreira` | Narón |
| 64 | test_o_val | 1 | 0.42279269 | `Monte do Castro (Castro de Vilasuso)` | Narón |
| 88 | test_o_val | 0 | 0.20636503 | `Mámoa do Val/Mámoa de Santa Margarida` | Narón |
| 166 | test_o_val | 1 | -0.49341152 | `Castro de Pena Lopesa` | Narón |

### test_trasancos

| Rank | Split | Class | Score | Name | Municipality |
|---:|---|---:|---:|---|---|
| 1 | test_trasancos | 1 | 6.53049690 | `Castro de Lobariz` | Ferrol |
| 2 | test_trasancos | 1 | 4.51217092 | `Necrópole de Santa Comba/Castro de Santa Comba` | Ferrol |
| 3 | test_trasancos | 1 | 3.61180386 | `Castro de Punta Taraza` | Valdoviño |
| 4 | test_trasancos | 1 | 2.57913878 | `Castro de Punta Frouxeira` | Valdoviño |
| 5 | test_trasancos | 1 | 2.57171448 | `Castros` | Neda |
| 6 | test_trasancos | 1 | 2.47618298 | `Castro de Vilasanche` | Ferrol |
| 7 | test_trasancos | 1 | 2.09125413 | `Castro de Viladonelle` | Neda |
| 8 | test_trasancos | 1 | 2.08607588 | `Castro das Pías/Castro de Cardoeiro` | Fene |
| 9 | test_trasancos | 1 | 1.94308726 | `Castro Das Croas` | San Sadurniño |
| 11 | test_trasancos | 1 | 1.66635124 | `Castro de Vilarrube/Os Castros de Ferreirías` | Valdoviño |

## O Val Relief Reading

- rank `10`: `O Castro (Castro de Quintá)` (positive), score `1.88998989`.
- rank `59`: `Castro da Pedreira` (positive), score `0.45731483`.
- rank `64`: `Monte do Castro (Castro de Vilasuso)` (positive), score `0.42279269`.
- rank `88`: `Mámoa do Val/Mámoa de Santa Margarida` (hard_negative), score `0.20636503`.
- rank `166`: `Castro de Pena Lopesa` (positive), score `-0.49341152`.

## Interpretation

Relief/MDT5 can detect broad topographic and radial contrast, but its 5 m grid is still coarse for buried walls or ditches. Treat this as a prioritization layer. Fine LiDAR/LAZ or richer derived products are still needed before candidate claims.
