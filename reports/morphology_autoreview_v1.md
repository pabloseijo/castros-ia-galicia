# Morphology Autoreview v1

Generated: 2026-08-01T00:00:00Z

## What This Is

Autonomous first-pass package over the P0 morphology queue. It creates provisional point, polygon and tile-window layers, plus official orthophoto thumbnails for a balanced control set v1.

This is still not a final archaeological label set. Every generated polygon is an auto-radius proxy around an official catalogue point. The field `training_use` is deliberately set to `exclude_until_visual_raster_verification`.

## Counts

- P0 rows processed: 839
- Control set v1 rows: 201
- Orthophoto thumbnails: 201
- Thumbnail status: {'exists': 200, 'failed': 1}

### P0 by Role/Country

- negative/ES: 278
- negative/PT: 181
- positive/ES: 210
- positive/PT: 170

### Control Set by Role/Country

- negative/ES: 60
- negative/PT: 41
- positive/ES: 57
- positive/PT: 43

### Control Positive Morphology

- coastal_promontory_hint: 38
- earthwork_or_wall_hint: 38
- large_castrexo_civitas_hint: 24

### Control Negative Types

- megalithic_mound: 50
- historic_fortification: 30
- megalithic_mound;rock_art_surface: 8
- roman_built_context: 6
- rock_art_surface: 4
- historic_fortification;roman_built_context: 2
- mining_or_quarry: 1

## Layers

- p0_points: 839
- p0_positive_proposed_polygons: 380
- p0_negative_proposed_polygons: 459
- control_set_v1_points: 201
- control_set_v1_positive_polygons: 100
- control_set_v1_negative_polygons: 101
- control_set_v1_tile_windows_512m: 201

## Files

- data/morphology-autoreview-v1/morphology_autoreview_v1.gpkg
- data/morphology-autoreview-v1/p0_points.geojson
- data/morphology-autoreview-v1/p0_positive_proposed_polygons.geojson
- data/morphology-autoreview-v1/p0_negative_proposed_polygons.geojson
- data/morphology-autoreview-v1/control_set_v1_points.geojson
- data/morphology-autoreview-v1/control_set_v1_positive_polygons.geojson
- data/morphology-autoreview-v1/control_set_v1_negative_polygons.geojson
- data/morphology-autoreview-v1/control_set_v1_tile_windows_512m.geojson
- data/morphology-autoreview-v1/autoreview_decisions.tsv
- data/morphology-autoreview-v1/orthophoto_thumbnail_manifest.tsv
- data/morphology-autoreview-v1/autoreview_summary.tsv

## Orthophoto Sources

- Galicia/Spain: IGN PNOA WMS `https://www.ign.es/wms-inspire/pnoa-ma`, layer `OI.OrthoimageCoverage`.
- Northern Portugal: DGT Ortofotos 2021 WMS `https://cartografia.dgterritorio.gov.pt/wms/ortos2021`, layer `Ortos2021-RGB`.

## Next Step

Run the radial/LiDAR/orthophoto feature extraction over `control_set_v1_*` first. Do not export these polygons to training manifests until a raster/visual verifier promotes them from `auto_seeded_requires_visual_verification` to `accepted`.
