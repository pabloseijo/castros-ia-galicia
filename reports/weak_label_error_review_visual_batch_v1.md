# Weak-label error review visual batch v1

Generated: 2026-08-01T00:00:00Z

## What This Is

Visual contact sheets for the first error-review batch. Each row combines RGB, DEM, slope and local relief with the same 120 m reference radius.
This is inspection material for deciding what the model confuses; it is not a discovery report.

## Sheets

### holdout_low_rank_positives

- rows: `25`
- image: `reports/figures/weak_label_error_review_v1/holdout-low-rank-positives.png`
- negative types: -=25
- morphology proxies: generic_castro_hint=15, croa_top_ring_hint=4, hilltop_hint=3, coastal_promontory_hint=2, valley_or_river_edge_hint=1
- relief status: valid=25

![holdout_low_rank_positives](reports/figures/weak_label_error_review_v1/holdout-low-rank-positives.png)

### holdout_morphology_rescues

- rows: `13`
- image: `reports/figures/weak_label_error_review_v1/holdout-morphology-rescues.png`
- negative types: -=13
- morphology proxies: generic_castro_hint=6, coastal_promontory_hint=3, hilltop_hint=2, croa_top_ring_hint=1, valley_or_river_edge_hint=1
- relief status: valid=13

![holdout_morphology_rescues](reports/figures/weak_label_error_review_v1/holdout-morphology-rescues.png)

### holdout_top_false_positives

- rows: `25`
- image: `reports/figures/weak_label_error_review_v1/holdout-top-false-positives.png`
- negative types: megalithic_mound=24, rock_art_surface=1
- morphology proxies: -=25
- relief status: valid=25

![holdout_top_false_positives](reports/figures/weak_label_error_review_v1/holdout-top-false-positives.png)

### val_low_rank_weak_positives

- rows: `12`
- image: `reports/figures/weak_label_error_review_v1/val-low-rank-weak-positives.png`
- negative types: -=12
- morphology proxies: generic_castro_hint=9, hilltop_hint=2, croa_top_ring_hint=1
- relief status: valid=12

![val_low_rank_weak_positives](reports/figures/weak_label_error_review_v1/val-low-rank-weak-positives.png)

### val_morphology_rescues

- rows: `12`
- image: `reports/figures/weak_label_error_review_v1/val-morphology-rescues.png`
- negative types: -=12
- morphology proxies: generic_castro_hint=9, hilltop_hint=2, croa_top_ring_hint=1
- relief status: valid=12

![val_morphology_rescues](reports/figures/weak_label_error_review_v1/val-morphology-rescues.png)

### val_top_weak_negatives

- rows: `12`
- image: `reports/figures/weak_label_error_review_v1/val-top-weak-negatives.png`
- negative types: megalithic_mound=8, historic_fortification=2, rock_art_surface=2
- morphology proxies: -=12
- relief status: valid=12

![val_top_weak_negatives](reports/figures/weak_label_error_review_v1/val-top-weak-negatives.png)

## O Val Focus

| Queue | Rank fusion | Rank max | Delta | Class | Name | Focus |
|---|---:|---:|---:|---:|---|---|
| `holdout_top_false_positives` | 80 | 99 | -19 | 0 | `Mámoa do Val/Mámoa de Santa Margarida` | negative high in fusion; inspect recurring distractor type |
| `holdout_low_rank_positives` | 199 | 72 | 127 | 1 | `Castro de Pena Lopesa` | positive low in fusion; inspect visibility, centering and morphology |
| `holdout_morphology_rescues` | 199 | 72 | 127 | 1 | `Castro de Pena Lopesa` | positive rescued by morphology channel; inspect archetype pattern |

## Reading

- Holdout false positives are dominated by `megalithic_mound` (`24`/25 in this visual batch), so the model is mainly confusing castros with archaeological relief distractors rather than random modern noise.
- Low-ranked positives are mixed morphology cases; top proxy in this batch is `generic_castro_hint` (`15`/25). These are the best candidates for hard-positive review.
- Use the holdout sheets before validation sheets. Holdouts explain local target behavior; validation sheets are weak-label stress tests.
- If a high-ranked negative visually looks like a plausible castro-like enclosure, keep it as `needs_review` rather than calling it a false positive.
