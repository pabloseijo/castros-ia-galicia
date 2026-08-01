# Weak-label splits v1

Generated: 2026-08-01T00:00:00Z

## What This Is

Broad provisional train/validation/test split for castro detection using the full morphology bank.
This is a weak-label dataset: catalogue points and catalogue non-castro distractors are supervision seeds, not final archaeological boundaries.

## Files

- `data/weak-label-splits-v1/weak_label_master.tsv`
- `data/weak-label-splits-v1/weak_label_train.tsv`
- `data/weak-label-splits-v1/weak_label_val.tsv`
- `data/weak-label-splits-v1/weak_label_test.tsv`
- `data/weak-label-splits-v1/weak_label_test_trasancos.tsv`
- `data/weak-label-splits-v1/weak_label_test_o_val.tsv`
- `data/weak-label-splits-v1/weak_label_excluded_review.tsv`
- `data/weak-label-splits-v1/weak_label_tile_manifest_512m.tsv`
- `data/weak-label-splits-v1/weak_label_points.geojson`
- `data/weak-label-splits-v1/weak_label_splits_v1.gpkg`

## Counts

- Master rows: 14774
- Original positive seeds retained in master: 3929
- Model-candidate rows: 13712
- Model positive candidates: 3003
- Model hard-negative candidates: 10709
- Holdout rows: 204
- Excluded/review-only rows: 858
- Tile manifest rows: 13916
- Mean visual score where known: 29.32

## Split Counts

- excluded_review/positive: 858
- test/hard_negative: 1966
- test/positive: 564
- test_o_val/hard_negative: 1
- test_o_val/positive: 4
- test_trasancos/hard_negative: 135
- test_trasancos/positive: 64
- train/hard_negative: 7131
- train/positive: 2014
- val/hard_negative: 1612
- val/positive: 425

## Weak-label Status

- exclude_ambiguous_positive_seed: 87
- exclude_low_toponymic_review: 1
- exclude_probable_name_false_positive: 770
- weak_hard_negative_candidate: 10845
- weak_positive_candidate: 3071

## Model Positive Morphology

- generic_castro_hint: 2022
- hilltop_hint: 382
- earthwork_or_wall_hint: 220
- coastal_promontory_hint: 136
- croa_top_ring_hint: 130
- valley_or_river_edge_hint: 65
- castrel_toponym_hint: 26
- large_castrexo_civitas_hint: 22

## Model Hard-negative Types

- megalithic_mound: 7388
- rock_art_surface: 2703
- roman_built_context: 220
- mining_or_quarry: 161
- necropolis_or_burial: 118
- historic_fortification: 81
- necropolis_or_burial;roman_built_context: 22
- megalithic_mound;rock_art_surface: 11
- rock_art_surface;roman_built_context: 3
- historic_fortification;roman_built_context: 2

## Spatial Policy

- Regular rows are split by administrative spatial block: `country|province_or_district|municipality`.
- O Val rows are forced to `test_o_val`.
- Fene, Ferrol, Narón, Neda, San Sadurniño and Valdoviño are forced to `test_trasancos`, except O Val, which has its own holdout.
- Rows with probable modern/toponymic false-positive risk stay in `excluded_review`.

## Leakage Check

- OK: no regular spatial block appears in multiple train/val/test splits.
- OK: no Trasancos municipality is used in model training.

## Training Use

`weak_label_candidate_for_model_v1` can feed a first weak detector.
`holdout_eval_only` is for evaluation and later inference over Trasancos/O Val.
`exclude_until_independent_label_review` rows should not train the model.

## Next Step

Use `weak_label_tile_manifest_512m.tsv` to export chips outside Git under `data/external/weak-label-chips-v1/`, then train a baseline classifier/segmenter with class weighting and spatial holdout evaluation.
