# Weak-label error review workspace v1

Generated: 2026-08-01T00:00:00Z

## Files

- GPKG: `data/weak-label-error-review-workspace-v1/weak_label_error_review_workspace_v1.gpkg`
- Tasks TSV: `data/weak-label-error-review-workspace-v1/review_lane_tasks.tsv`
- Taxonomy TSV: `data/weak-label-error-review-workspace-v1/review_taxonomy.tsv`
- Lane GeoJSON dir: `data/weak-label-error-review-workspace-v1/lanes`

## Counts

- total tasks: `213`

### By Priority

- `P0`: 32
- `P1`: 111
- `P2`: 70

### By Lane

- `morphology_rescue_review`: 94
- `mamoa_false_positive_review`: 63
- `low_positive_review`: 36
- `weak_negative_review`: 12
- `mamoa_specialist_positive_review`: 8

### By Suggested Taxonomy

- `castro`: 138
- `mamoa`: 63
- `petroglifo`: 8
- `fortificacion_historica`: 4

## O Val Focus

| Review ID | Lane | Priority | Fusion rank | Max rank | Specialist rank | Suggested taxonomy | Name |
|---|---|---|---:|---:|---:|---|---|
| `err-review-0023` | `mamoa_false_positive_review` | `P0` | 80 | 99 | 95 | `mamoa` | `Mámoa do Val/Mámoa de Santa Margarida` |
| `err-review-0025` | `mamoa_specialist_positive_review` | `P0` | 199 | 72 | 2 | `castro` | `Castro de Pena Lopesa` |
| `err-review-0028` | `mamoa_specialist_positive_review` | `P0` | 199 | 72 | 2 | `castro` | `Castro de Pena Lopesa` |

## Interpretation

- This package turns the model-error queue into QGIS layers that can be opened independently.
- `mamoa_false_positive_review` should not be treated as generic background: these are archaeological hard negatives.
- `mamoa_specialist_positive_review` is the key rescue lane for positives that the global fusion suppresses.
- No row in this package is a new site claim; every decision remains a review decision.
