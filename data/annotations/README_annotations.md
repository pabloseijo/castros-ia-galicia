# Annotation workspace

Generated: 2026-07-31

Open `castros_annotations.gpkg` in QGIS together with `../qgis-review/castros_trasancos_qgis_review.gpkg`.

Editable layers:

- `labels_reviewed`: final positive polygons drawn by the human reviewer.
- `negative_areas_reviewed`: final negative polygons accepted by the human reviewer.
- `geocoded_sites_reviewed`: corrected/geocoded points for sites that were missing coordinates.
- `site_review_decisions`: one decision row per source site/task.
- `negative_review_decisions`: one decision row per generated hard-negative point.

Do not edit generated layers in `data/qgis-review`; copy or trace into these annotation layers.
