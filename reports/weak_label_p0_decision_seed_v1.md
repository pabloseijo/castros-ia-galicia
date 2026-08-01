# Weak-label P0 decision seed v1

Generated: 2026-08-01T00:00:00Z

## What This Is

This is an autonomous decision seed for the P0 weak-label review queue.
It is not a final annotation layer, not an archaeological discovery report, and not a strong training dataset.
Every row keeps `autonomous_seed_status=proposed_not_final`, `accepted_label_status=not_accepted` and `can_enter_training_now=no`.

## Outputs

- TSV: `data/weak-label-error-review-workspace-v1/p0_decision_seed.tsv`
- GeoJSON points: `data/weak-label-error-review-workspace-v1/p0_decision_seed.geojson`
- GeoPackage: `data/weak-label-error-review-workspace-v1/p0_decision_seed_v1.gpkg`
- GPKG layer: `p0_decision_seed_points`
- GPKG layer: `p0_review_buffers_120m`

## Counts

- rows: `30`

### Suggested taxonomy

- `mamoa`: `24`
- `castro`: `6`

### Autonomous decision

- `confirm_specific_archaeological_hard_negative`: `24`
- `positive_boundary_review_required`: `6`

### Training gate

- `eligible_only_after_taxonomy_confirmation`: `24`
- `needs_reviewed_polygon_before_strong_training`: `6`

## Review Order

| Order | Taxonomy | Autonomous decision | Training gate | Name | Card |
|---:|---|---|---|---|---|
| 01 | `castro` | `positive_boundary_review_required` | `needs_reviewed_polygon_before_strong_training` | `Castro de Pena Lopesa` | `reports/figures/weak_label_p0_pretriage_v1/p0-01-castro-de-pena-lopesa.png` |
| 02 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa do Val/Mámoa de Santa Margarida` | `reports/figures/weak_label_p0_pretriage_v1/p0-02-mamoa-do-val-mamoa-de-santa-margarida.png` |
| 03 | `castro` | `positive_boundary_review_required` | `needs_reviewed_polygon_before_strong_training` | `Castro de Punta Taraza` | `reports/figures/weak_label_p0_pretriage_v1/p0-03-castro-de-punta-taraza.png` |
| 04 | `castro` | `positive_boundary_review_required` | `needs_reviewed_polygon_before_strong_training` | `Castro de Punta Frouxeira` | `reports/figures/weak_label_p0_pretriage_v1/p0-04-castro-de-punta-frouxeira.png` |
| 05 | `castro` | `positive_boundary_review_required` | `needs_reviewed_polygon_before_strong_training` | `Necrópole de Santa Comba/Castro de Santa Comba` | `reports/figures/weak_label_p0_pretriage_v1/p0-05-necropole-de-santa-comba-castro-de-santa-comba.png` |
| 06 | `castro` | `positive_boundary_review_required` | `needs_reviewed_polygon_before_strong_training` | `Castro da Punta do Vico` | `reports/figures/weak_label_p0_pretriage_v1/p0-06-castro-da-punta-do-vico.png` |
| 07 | `castro` | `positive_boundary_review_required` | `needs_reviewed_polygon_before_strong_training` | `Castro de Coto Redondo` | `reports/figures/weak_label_p0_pretriage_v1/p0-07-castro-de-coto-redondo.png` |
| 08 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa do Rego da Moa` | `reports/figures/weak_label_p0_pretriage_v1/p0-08-mamoa-do-rego-da-moa.png` |
| 09 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Pena Moura` | `reports/figures/weak_label_p0_pretriage_v1/p0-09-mamoa-de-pena-moura.png` |
| 10 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa do Monte Marraxón IV-1` | `reports/figures/weak_label_p0_pretriage_v1/p0-10-mamoa-do-monte-marraxon-iv-1.png` |
| 11 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Coto da Fraga 2` | `reports/figures/weak_label_p0_pretriage_v1/p0-11-mamoa-de-coto-da-fraga-2.png` |
| 12 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa do Monte de Pena Moura 3` | `reports/figures/weak_label_p0_pretriage_v1/p0-12-mamoa-do-monte-de-pena-moura-3.png` |
| 13 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa do Monte dos Niños 05` | `reports/figures/weak_label_p0_pretriage_v1/p0-13-mamoa-do-monte-dos-ninos-05.png` |
| 14 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Bardaos` | `reports/figures/weak_label_p0_pretriage_v1/p0-14-mamoa-de-bardaos.png` |
| 15 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Rioboo 1/Mámoa de Canteiros 1` | `reports/figures/weak_label_p0_pretriage_v1/p0-15-mamoa-de-rioboo-1-mamoa-de-canteiros-1.png` |
| 16 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa dos Montes de Brión III-8` | `reports/figures/weak_label_p0_pretriage_v1/p0-16-mamoa-dos-montes-de-brion-iii-8.png` |
| 17 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa dos Montes de Brión IV-7` | `reports/figures/weak_label_p0_pretriage_v1/p0-17-mamoa-dos-montes-de-brion-iv-7.png` |
| 18 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa dos Montes de Brión VI-1` | `reports/figures/weak_label_p0_pretriage_v1/p0-18-mamoa-dos-montes-de-brion-vi-1.png` |
| 19 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa dos Montes de Brión I-10` | `reports/figures/weak_label_p0_pretriage_v1/p0-19-mamoa-dos-montes-de-brion-i-10.png` |
| 20 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Muíño do Vento` | `reports/figures/weak_label_p0_pretriage_v1/p0-20-mamoa-de-muino-do-vento.png` |
| 21 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Loira` | `reports/figures/weak_label_p0_pretriage_v1/p0-21-mamoa-de-loira.png` |
| 22 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Mougá 6` | `reports/figures/weak_label_p0_pretriage_v1/p0-22-mamoa-de-mouga-6.png` |
| 23 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa dos Montes de Brión I-7` | `reports/figures/weak_label_p0_pretriage_v1/p0-23-mamoa-dos-montes-de-brion-i-7.png` |
| 24 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa dos Montes de Brión I-1` | `reports/figures/weak_label_p0_pretriage_v1/p0-24-mamoa-dos-montes-de-brion-i-1.png` |
| 25 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa dos Montes de Brión I-6` | `reports/figures/weak_label_p0_pretriage_v1/p0-25-mamoa-dos-montes-de-brion-i-6.png` |
| 26 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Pena Escrita` | `reports/figures/weak_label_p0_pretriage_v1/p0-26-mamoa-de-pena-escrita.png` |
| 27 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Rioboo 2/Mámoa de Canteiros 2/M moas do Val` | `reports/figures/weak_label_p0_pretriage_v1/p0-27-mamoa-de-rioboo-2-mamoa-de-canteiros-2-m-moas-do-val.png` |
| 28 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Leixa 2` | `reports/figures/weak_label_p0_pretriage_v1/p0-28-mamoa-de-leixa-2.png` |
| 29 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Leixa 3/Mámoa de Trasancos` | `reports/figures/weak_label_p0_pretriage_v1/p0-29-mamoa-de-leixa-3-mamoa-de-trasancos.png` |
| 30 | `mamoa` | `confirm_specific_archaeological_hard_negative` | `eligible_only_after_taxonomy_confirmation` | `Mámoa de Leixa 1` | `reports/figures/weak_label_p0_pretriage_v1/p0-30-mamoa-de-leixa-1.png` |

## Use In QGIS

1. Open `p0_decision_seed_v1.gpkg` together with `weak_label_error_review_workspace_v1.gpkg`.
2. Use `p0_review_buffers_120m` only as a search area.
3. For castros, draw a reviewed boundary in the editable annotation workspace only when the form is defensible.
4. For mamoas, confirm taxonomy as a specific archaeological hard negative; do not convert it into generic absence.
5. Leave uncertain cases as `non_decidible`.
