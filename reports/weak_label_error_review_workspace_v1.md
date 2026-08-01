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

## P0 Pretriage

| Order | Group | Decision | Confidence | Lane | Specialist rank | Name |
|---:|---|---|---|---|---:|---|
| 1 | `o_val_local_first` | `local_positive_boundary_review` | `high_model_signal_boundary_needed` | `mamoa_specialist_positive_review` | 2 | `Castro de Pena Lopesa` |
| 2 | `o_val_local_first` | `confirm_local_mamoa_non_castro_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 95 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 3 | `positive_rescue` | `positive_boundary_review` | `high_model_signal_boundary_needed` | `mamoa_specialist_positive_review` | 1 | `Castro de Punta Taraza` |
| 4 | `positive_rescue` | `positive_boundary_review` | `high_model_signal_boundary_needed` | `mamoa_specialist_positive_review` | 3 | `Castro de Punta Frouxeira` |
| 5 | `positive_rescue` | `positive_boundary_review` | `medium_model_signal_boundary_needed` | `mamoa_specialist_positive_review` | 4 | `Necrópole de Santa Comba/Castro de Santa Comba` |
| 6 | `positive_rescue` | `positive_boundary_review` | `medium_model_signal_boundary_needed` | `mamoa_specialist_positive_review` | 6 | `Castro da Punta do Vico` |
| 7 | `positive_rescue` | `positive_boundary_review` | `medium_model_signal_boundary_needed` | `mamoa_specialist_positive_review` | 8 | `Castro de Coto Redondo` |
| 8 | `mamoa_strong_model_confuser` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_high_confusion` | `mamoa_false_positive_review` | 18 | `Mámoa do Rego da Moa` |
| 9 | `mamoa_strong_model_confuser` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_high_confusion` | `mamoa_false_positive_review` | 34 | `Mámoa de Pena Moura` |
| 10 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 47 | `Mámoa do Monte Marraxón IV-1` |
| 11 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 51 | `Mámoa de Coto da Fraga 2` |
| 12 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 52 | `Mámoa do Monte de Pena Moura 3` |
| 13 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 55 | `Mámoa do Monte dos Niños 05` |
| 14 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 58 | `Mámoa de Bardaos` |
| 15 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 59 | `Mámoa de Rioboo 1/Mámoa de Canteiros 1` |
| 16 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 60 | `Mámoa dos Montes de Brión III-8` |
| 17 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 63 | `Mámoa dos Montes de Brión IV-7` |
| 18 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 64 | `Mámoa dos Montes de Brión VI-1` |
| 19 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 65 | `Mámoa dos Montes de Brión I-10` |
| 20 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 66 | `Mámoa de Muíño do Vento` |
| 21 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 71 | `Mámoa de Loira` |
| 22 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 75 | `Mámoa de Mougá 6` |
| 23 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 82 | `Mámoa dos Montes de Brión I-7` |
| 24 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 84 | `Mámoa dos Montes de Brión I-1` |
| 25 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 92 | `Mámoa dos Montes de Brión I-6` |
| 26 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 109 | `Mámoa de Pena Escrita` |
| 27 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 110 | `Mámoa de Rioboo 2/Mámoa de Canteiros 2/M moas do Val` |
| 28 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 115 | `Mámoa de Leixa 2` |
| 29 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 133 | `Mámoa de Leixa 3/Mámoa de Trasancos` |
| 30 | `mamoa_archaeological_hard_negative` | `confirm_mamoa_specific_hard_negative` | `high_taxonomy_medium_confusion` | `mamoa_false_positive_review` | 142 | `Mámoa de Leixa 1` |

## Interpretation

- This package turns the model-error queue into QGIS layers that can be opened independently.
- `mamoa_false_positive_review` should not be treated as generic background: these are archaeological hard negatives.
- `mamoa_specialist_positive_review` is the key rescue lane for positives that the global fusion suppresses.
- `p0_pretriage` is an autonomous first-pass triage, not a final archaeological decision.
- No row in this package is a new site claim; every decision remains a review decision.
