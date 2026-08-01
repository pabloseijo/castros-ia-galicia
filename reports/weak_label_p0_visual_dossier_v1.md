# Weak-label P0 pretriage visual dossier v1

Generated: 2026-08-01T00:00:00Z

## What This Is

This dossier turns the autonomous P0 pretriage queue into inspectable visual cards.
Each card combines RGB, DEM, slope and local relief with the same 120 m reference radius used by the broader error-review figures.
It is a review aid, not an archaeological acceptance/rejection decision and not a discovery report.

## Outputs

- P0 input rows: `32`
- Unique P0 points after duplicate collapse: `30`
- Dossier TSV: `data/weak-label-error-review-workspace-v1/p0_visual_dossier.tsv`
- Full sheet: `reports/figures/weak_label_p0_pretriage_v1/p0-pretriage-all.png`
- Individual cards: `reports/figures/weak_label_p0_pretriage_v1/p0-*.png`

## Counts

### Groups

- `o_val_local_first`: `2`
- `positive_rescue`: `5`
- `mamoa_strong_model_confuser`: `2`
- `mamoa_archaeological_hard_negative`: `21`

### Source lanes

- `mamoa_false_positive_review`: `24`
- `mamoa_specialist_positive_review`: `6`

### Suggested taxonomy

- `mamoa`: `24`
- `castro`: `6`

## Group Sheets

### O Val local first

- rows: `2`
- image: `reports/figures/weak_label_p0_pretriage_v1/p0-pretriage-o-val-local-first.png`

![o_val_local_first](reports/figures/weak_label_p0_pretriage_v1/p0-pretriage-o-val-local-first.png)

### positive rescue

- rows: `5`
- image: `reports/figures/weak_label_p0_pretriage_v1/p0-pretriage-positive-rescue.png`

![positive_rescue](reports/figures/weak_label_p0_pretriage_v1/p0-pretriage-positive-rescue.png)

### mamoa strong model confuser

- rows: `2`
- image: `reports/figures/weak_label_p0_pretriage_v1/p0-pretriage-mamoa-strong-model-confuser.png`

![mamoa_strong_model_confuser](reports/figures/weak_label_p0_pretriage_v1/p0-pretriage-mamoa-strong-model-confuser.png)

### mamoa archaeological hard negative

- rows: `21`
- image: `reports/figures/weak_label_p0_pretriage_v1/p0-pretriage-mamoa-archaeological-hard-negative.png`

![mamoa_archaeological_hard_negative](reports/figures/weak_label_p0_pretriage_v1/p0-pretriage-mamoa-archaeological-hard-negative.png)

## O Val Local First

| Order | Class | Name | Decision | Fusion rank | Max rank | Specialist rank | Card |
|---:|---:|---|---|---:|---:|---:|---|
| 01 | 1 | `Castro de Pena Lopesa` | `local_positive_boundary_review` | 199 | 72 | 2 | `reports/figures/weak_label_p0_pretriage_v1/p0-01-castro-de-pena-lopesa.png` |
| 02 | 0 | `Mámoa do Val/Mámoa de Santa Margarida` | `confirm_local_mamoa_non_castro_hard_negative` | 80 | 99 | 95 | `reports/figures/weak_label_p0_pretriage_v1/p0-02-mamoa-do-val-mamoa-de-santa-margarida.png` |

## Full P0 Order

| Order | Group | Class | Taxonomy | Name | Municipality | Decision | Source queues | Card |
|---:|---|---:|---|---|---|---|---|---|
| 01 | `o_val_local_first` | 1 | `castro` | `Castro de Pena Lopesa` | `Narón` | `local_positive_boundary_review` | `holdout_low_rank_positives;holdout_morphology_rescues` | `reports/figures/weak_label_p0_pretriage_v1/p0-01-castro-de-pena-lopesa.png` |
| 02 | `o_val_local_first` | 0 | `mamoa` | `Mámoa do Val/Mámoa de Santa Margarida` | `Narón` | `confirm_local_mamoa_non_castro_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-02-mamoa-do-val-mamoa-de-santa-margarida.png` |
| 03 | `positive_rescue` | 1 | `castro` | `Castro de Punta Taraza` | `Valdoviño` | `positive_boundary_review` | `holdout_morphology_rescues` | `reports/figures/weak_label_p0_pretriage_v1/p0-03-castro-de-punta-taraza.png` |
| 04 | `positive_rescue` | 1 | `castro` | `Castro de Punta Frouxeira` | `Valdoviño` | `positive_boundary_review` | `holdout_morphology_rescues` | `reports/figures/weak_label_p0_pretriage_v1/p0-04-castro-de-punta-frouxeira.png` |
| 05 | `positive_rescue` | 1 | `castro` | `Necrópole de Santa Comba/Castro de Santa Comba` | `Ferrol` | `positive_boundary_review` | `holdout_morphology_rescues` | `reports/figures/weak_label_p0_pretriage_v1/p0-05-necropole-de-santa-comba-castro-de-santa-comba.png` |
| 06 | `positive_rescue` | 1 | `castro` | `Castro da Punta do Vico` | `Valdoviño` | `positive_boundary_review` | `holdout_low_rank_positives;holdout_morphology_rescues` | `reports/figures/weak_label_p0_pretriage_v1/p0-06-castro-da-punta-do-vico.png` |
| 07 | `positive_rescue` | 1 | `castro` | `Castro de Coto Redondo` | `Valdoviño` | `positive_boundary_review` | `holdout_low_rank_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-07-castro-de-coto-redondo.png` |
| 08 | `mamoa_strong_model_confuser` | 0 | `mamoa` | `Mámoa do Rego da Moa` | `Fene` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-08-mamoa-do-rego-da-moa.png` |
| 09 | `mamoa_strong_model_confuser` | 0 | `mamoa` | `Mámoa de Pena Moura` | `Valdoviño` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-09-mamoa-de-pena-moura.png` |
| 10 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa do Monte Marraxón IV-1` | `Fene` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-10-mamoa-do-monte-marraxon-iv-1.png` |
| 11 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Coto da Fraga 2` | `Valdoviño` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-11-mamoa-de-coto-da-fraga-2.png` |
| 12 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa do Monte de Pena Moura 3` | `Valdoviño` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-12-mamoa-do-monte-de-pena-moura-3.png` |
| 13 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa do Monte dos Niños 05` | `Narón` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-13-mamoa-do-monte-dos-ninos-05.png` |
| 14 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Bardaos` | `San Sadurniño` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-14-mamoa-de-bardaos.png` |
| 15 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Rioboo 1/Mámoa de Canteiros 1` | `Valdoviño` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-15-mamoa-de-rioboo-1-mamoa-de-canteiros-1.png` |
| 16 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa dos Montes de Brión III-8` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-16-mamoa-dos-montes-de-brion-iii-8.png` |
| 17 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa dos Montes de Brión IV-7` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-17-mamoa-dos-montes-de-brion-iv-7.png` |
| 18 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa dos Montes de Brión VI-1` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-18-mamoa-dos-montes-de-brion-vi-1.png` |
| 19 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa dos Montes de Brión I-10` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-19-mamoa-dos-montes-de-brion-i-10.png` |
| 20 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Muíño do Vento` | `Narón` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-20-mamoa-de-muino-do-vento.png` |
| 21 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Loira` | `Valdoviño` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-21-mamoa-de-loira.png` |
| 22 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Mougá 6` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-22-mamoa-de-mouga-6.png` |
| 23 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa dos Montes de Brión I-7` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-23-mamoa-dos-montes-de-brion-i-7.png` |
| 24 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa dos Montes de Brión I-1` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-24-mamoa-dos-montes-de-brion-i-1.png` |
| 25 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa dos Montes de Brión I-6` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-25-mamoa-dos-montes-de-brion-i-6.png` |
| 26 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Pena Escrita` | `San Sadurniño` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-26-mamoa-de-pena-escrita.png` |
| 27 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Rioboo 2/Mámoa de Canteiros 2/M moas do Val` | `Valdoviño` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-27-mamoa-de-rioboo-2-mamoa-de-canteiros-2-m-moas-do-val.png` |
| 28 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Leixa 2` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-28-mamoa-de-leixa-2.png` |
| 29 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Leixa 3/Mámoa de Trasancos` | `Narón` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-29-mamoa-de-leixa-3-mamoa-de-trasancos.png` |
| 30 | `mamoa_archaeological_hard_negative` | 0 | `mamoa` | `Mámoa de Leixa 1` | `Ferrol` | `confirm_mamoa_specific_hard_negative` | `holdout_top_false_positives` | `reports/figures/weak_label_p0_pretriage_v1/p0-30-mamoa-de-leixa-1.png` |

## Next Review Move

1. Open the `p0_pretriage` layer in the QGIS workspace.
2. Use the dossier order as the review order.
3. For positive castros, draw or refine the visible boundary only when RGB/relief/source context supports it.
4. For mamoas, confirm them as specific archaeological hard negatives and do not reuse them as generic absence.
5. Leave ambiguous points as `non_decidible` or `needs_followup` rather than forcing labels.
