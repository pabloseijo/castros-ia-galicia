# Weak-label error review workspace v1

Generated: 2026-08-01T00:00:00Z

## What This Is

QGIS-ready package for reviewing the weak-label RGB+relief error queue by lane.
It is a review workspace, not an archaeological discovery report.

## Files

- `weak_label_error_review_workspace_v1.gpkg`: all lanes as QGIS layers plus a decision template table.
- `review_lane_tasks.tsv`: task table sorted by priority/lane.
- `review_taxonomy.tsv`: minimal taxonomy for first-pass decisions.
- `lanes/*.geojson`: one lightweight GeoJSON per lane.

## Recommended Order

1. Open `p0_pretriage` first.
2. Filter or open `lane_mamoa_false_positive`.
3. Then inspect `lane_mamoa_specialist_positive`.
4. Then inspect `lane_morphology_rescue`.
5. Leave validation weak negatives for a later, lower-confidence batch.

## Fields To Use

- `review_lane`: why the point is in the workspace.
- `duplicate_count` / `duplicate_queues`: whether the same sample appears in multiple queues.
- `pretriage_order`, `pretriage_group`, `pretriage_decision`: autonomous first-pass ordering and action.
- `suggested_taxonomy`: first-pass category, not final truth.
- `suggested_decision`: proposed action.
- `boundary_action`: what to draw/confirm in QGIS.
- `review_status`, `final_taxonomy`, `final_decision`, `review_notes`: editable decision fields.

## Layer Counts

- `all_error_review_points`: 213
- `unique_error_review_points`: 177
- `lane_mamoa_false_positive`: 63
- `lane_mamoa_specialist_positive`: 8
- `lane_morphology_rescue`: 94
- `lane_low_positive`: 36
- `lane_weak_negative`: 12
- `o_val_focus`: 3
- `p0_first_pass`: 32
- `p0_unique_first_pass`: 30
- `p0_pretriage`: 30
