# Weak-label error review queue v1

Generated: 2026-08-01T00:00:00Z

## What This Is

A QGIS-ready review queue derived from the RGB+relief fusion baseline and the morphology safety blend.
It turns model errors into inspection tasks: high-ranked hard negatives, low-ranked known positives and morphology rescues.

## Files

- Queue TSV: `data/weak-label-fusion-v1/weak_label_error_review_queue.tsv`
- Queue GeoJSON: `data/weak-label-fusion-v1/weak_label_error_review_queue.geojson`

## Queue Counts

- `holdout_low_rank_positives`: 25
- `holdout_morphology_rescues`: 13
- `holdout_top_false_positives`: 25
- `val_low_rank_weak_positives`: 50
- `val_morphology_rescues`: 50
- `val_top_weak_negatives`: 50

## O Val Rows In Queue

| Queue | Lane | Fusion rank | Max-safety rank | Specialist rank | Mean rank | Delta | Class | Name | Reason |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| `holdout_top_false_positives` | `mamoa_false_positive_review` | 80 | 99 | 95 | 90 | -19 | 0 | `Mámoa do Val/Mámoa de Santa Margarida` | Known hard negative ranked high by the main fusion model; inspect as false-positive pattern. |
| `holdout_low_rank_positives` | `mamoa_specialist_positive_review` | 199 | 72 | 2 | 51 | 127 | 1 | `Castro de Pena Lopesa` | Known positive ranked low by the main fusion model; inspect as false-negative morphology. |
| `holdout_morphology_rescues` | `mamoa_specialist_positive_review` | 199 | 72 | 2 | 51 | 127 | 1 | `Castro de Pena Lopesa` | Known positive moved upward by max_safety; inspect morphology archetype missed by the main model. |

## Interpretation

- Start QGIS inspection with `holdout_top_false_positives` and `holdout_low_rank_positives`; these explain what the model confuses in the local target area.
- Use `holdout_morphology_rescues` as the sanity check for rare forms such as `Castro de Pena Lopesa`.
- Use `mamoa_false_positive_review` and `mamoa_specialist_positive_review` to separate castro-vs-mamoa confusion from general morphology failure.
- Validation queues are weak-label queues, not archaeological truth: a high-ranked negative may be a mislabeled absence, not a model error.
