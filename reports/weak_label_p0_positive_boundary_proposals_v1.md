# Weak-label P0 positive boundary proposals v1

Generated: 2026-08-01T00:00:00Z

## What This Is

Rough relief-derived geometry proposals for the six P0 positive castros.
These are QGIS tracing aids, not accepted archaeological boundaries and not training labels.
Every row keeps `proposal_status=rough_relief_proposal_not_label`, `accepted_label_status=not_accepted` and `can_enter_training_now=no`.

## Outputs

- TSV: `data/weak-label-error-review-workspace-v1/p0_positive_boundary_proposals.tsv`
- GeoJSON: `data/weak-label-error-review-workspace-v1/p0_positive_boundary_proposals.geojson`
- GeoPackage: `data/weak-label-error-review-workspace-v1/p0_positive_boundary_proposals_v1.gpkg`
- GPKG layer: `p0_positive_boundary_proposals`

## Counts

- proposals: `6`

## Proposal Table

| Order | Name | Method | Area m2 | Card |
|---:|---|---|---:|---|
| 01 | `Castro de Pena Lopesa` | `hilltop_dem_lrm_component` | 44415.8 | `reports/figures/weak_label_p0_pretriage_v1/p0-01-castro-de-pena-lopesa.png` |
| 03 | `Castro de Punta Taraza` | `promontory_slope_lrm_component` | 36696.2 | `reports/figures/weak_label_p0_pretriage_v1/p0-03-castro-de-punta-taraza.png` |
| 04 | `Castro de Punta Frouxeira` | `promontory_slope_lrm_component` | 34048.1 | `reports/figures/weak_label_p0_pretriage_v1/p0-04-castro-de-punta-frouxeira.png` |
| 05 | `Necrópole de Santa Comba/Castro de Santa Comba` | `generic_relief_component` | 31010.5 | `reports/figures/weak_label_p0_pretriage_v1/p0-05-necropole-de-santa-comba-castro-de-santa-comba.png` |
| 06 | `Castro da Punta do Vico` | `promontory_slope_lrm_component` | 24880.8 | `reports/figures/weak_label_p0_pretriage_v1/p0-06-castro-da-punta-do-vico.png` |
| 07 | `Castro de Coto Redondo` | `hilltop_dem_lrm_component` | 38916.0 | `reports/figures/weak_label_p0_pretriage_v1/p0-07-castro-de-coto-redondo.png` |

## Use In QGIS

1. Open this GPKG together with `p0_decision_seed_v1.gpkg` and the visual dossier.
2. Treat every polygon as a sketch/tracing aid.
3. If a boundary is defensible, redraw it into the editable annotation workspace; do not copy it blindly.
4. If the proposal follows a cliff, beach, vegetation edge or terrain artifact instead of a castro boundary, mark the case as `needs_followup`.
