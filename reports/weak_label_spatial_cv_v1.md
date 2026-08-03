# Weak-label spatial cross-validation v1

Generated at: `2026-08-02T00:00:00Z`
Rows: `13079` · spatial blocks: `314` · folds: `5`

## Why this exists

The headline v1 numbers (`val` AUC `0.905931`, `test` AUC `0.910299`,
holdouts AUC `0.925281`) come from one spatial cut. They are a single
draw. This run refits the same fusion under repeated spatially blocked
folds to report a range, and under random folds to measure how much
spatial autocorrelation would have inflated the same model.

## Summary

| regime | feature set | folds | ROC-AUC mean | ROC-AUC std | ROC-AUC min | ROC-AUC max | AP mean | AP std |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `block` | `fusion` | `5` | `0.913092` | `0.006893` | `0.902997` | `0.922278` | `0.790352` | `0.025928` |
| `random` | `fusion` | `5` | `0.914506` | `0.002401` | `0.911451` | `0.918586` | `0.792346` | `0.010721` |
| `block` | `fusion_plus_msrm` | `5` | `0.931854` | `0.005982` | `0.921660` | `0.940035` | `0.826888` | `0.019509` |
| `random` | `fusion_plus_msrm` | `5` | `0.933045` | `0.002883` | `0.927785` | `0.935805` | `0.828926` | `0.012090` |

**Autocorrelation premium (random minus block, fusion ROC-AUC): `+0.001414`.**

Any figure quoted from a random split carries this much unearned
credit. Only the blocked number describes moving to new ground.

## Feature sets compared

| feature set | columns |
|---|---:|
| `fusion` | `43` |
| `fusion_plus_msrm` | `70` |

## Per-fold detail

| regime | fold | train rows | test rows | positives | blocks held out | ROC-AUC | AP | P@50 | R@50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `block` | `1` | `10543` | `2536` | `560` | `61` | `0.910012` | `0.787692` | `0.980000` | `0.087500` |
| `block` | `2` | `10397` | `2682` | `560` | `62` | `0.910970` | `0.784866` | `0.960000` | `0.085714` |
| `block` | `3` | `10200` | `2879` | `559` | `69` | `0.902997` | `0.749181` | `0.940000` | `0.084079` |
| `block` | `4` | `10357` | `2722` | `560` | `61` | `0.922278` | `0.800636` | `0.960000` | `0.085714` |
| `block` | `5` | `10819` | `2260` | `560` | `61` | `0.919201` | `0.829383` | `0.980000` | `0.087500` |
| `random` | `1` | `10463` | `2616` | `540` | `276` | `0.914634` | `0.775423` | `0.920000` | `0.085185` |
| `random` | `2` | `10463` | `2616` | `559` | `279` | `0.911451` | `0.790138` | `0.980000` | `0.087657` |
| `random` | `3` | `10463` | `2616` | `604` | `281` | `0.912888` | `0.807986` | `0.960000` | `0.079470` |
| `random` | `4` | `10463` | `2616` | `560` | `283` | `0.918586` | `0.798135` | `0.980000` | `0.087500` |
| `random` | `5` | `10464` | `2615` | `536` | `280` | `0.914973` | `0.790049` | `0.960000` | `0.089552` |
| `block` | `1` | `10543` | `2536` | `560` | `61` | `0.930810` | `0.834255` | `0.980000` | `0.087500` |
| `block` | `2` | `10397` | `2682` | `560` | `62` | `0.932302` | `0.829314` | `0.960000` | `0.085714` |
| `block` | `3` | `10200` | `2879` | `559` | `69` | `0.921660` | `0.792055` | `0.960000` | `0.085868` |
| `block` | `4` | `10357` | `2722` | `560` | `61` | `0.940035` | `0.826839` | `0.960000` | `0.085714` |
| `block` | `5` | `10819` | `2260` | `560` | `61` | `0.934463` | `0.851978` | `0.960000` | `0.085714` |
| `random` | `1` | `10463` | `2616` | `540` | `276` | `0.934756` | `0.809117` | `0.900000` | `0.083333` |
| `random` | `2` | `10463` | `2616` | `559` | `279` | `0.934668` | `0.843598` | `1.000000` | `0.089445` |
| `random` | `3` | `10463` | `2616` | `604` | `281` | `0.927785` | `0.838182` | `0.980000` | `0.081126` |
| `random` | `4` | `10463` | `2616` | `560` | `283` | `0.935805` | `0.830679` | `0.980000` | `0.087500` |
| `random` | `5` | `10464` | `2615` | `536` | `280` | `0.932209` | `0.823056` | `1.000000` | `0.093284` |

## Blocks the ranker does not recover (out-of-fold, top-decile recall < 0.5)

Blocks with positives: `306` · below half recall: `166`

| block | province/district | municipality | positives | recovered | recall | median positive rank pct |
|---|---|---|---:|---:|---:|---:|
| `ES|A Coruña|Oroso` | A Coruña | Oroso | `18` | `0` | `0.000000` | `0.267796` |
| `ES|A Coruña|Sada` | A Coruña | Sada | `13` | `0` | `0.000000` | `0.248872` |
| `ES|A Coruña|Dodro` | A Coruña | Dodro | `8` | `0` | `0.000000` | `0.271810` |
| `ES|A Coruña|Oleiros` | A Coruña | Oleiros | `8` | `0` | `0.000000` | `0.181015` |
| `ES|A Coruña|A Baña` | A Coruña | A Baña | `8` | `0` | `0.000000` | `0.163086` |
| `ES|A Coruña|Mugardos` | A Coruña | Mugardos | `6` | `0` | `0.000000` | `0.222112` |
| `ES|Pontevedra|Meis` | Pontevedra | Meis | `6` | `0` | `0.000000` | `0.265540` |
| `ES|Ourense|O Irixo` | Ourense | O Irixo | `6` | `0` | `0.000000` | `0.181359` |
| `ES|Pontevedra|Moraña` | Pontevedra | Moraña | `6` | `0` | `0.000000` | `0.271733` |
| `ES|Ourense|Vilar de Barrio` | Ourense | Vilar de Barrio | `4` | `0` | `0.000000` | `0.177307` |
| `ES|A Coruña|Padrón` | A Coruña | Padrón | `4` | `0` | `0.000000` | `0.209037` |
| `ES|Pontevedra|A Guarda` | Pontevedra | A Guarda | `4` | `0` | `0.000000` | `0.309045` |
| `ES|Ourense|Beade` | Ourense | Beade | `4` | `0` | `0.000000` | `0.347542` |
| `ES|Pontevedra|Cerdedo Cotobade` | Pontevedra | Cerdedo Cotobade | `4` | `0` | `0.000000` | `0.817685` |
| `ES|Ourense|Baños de Molgas` | Ourense | Baños de Molgas | `4` | `0` | `0.000000` | `0.275900` |
| `ES|Ourense|Sarreaus` | Ourense | Sarreaus | `4` | `0` | `0.000000` | `0.220850` |
| `ES|Ourense|Castrelo do Val` | Ourense | Castrelo do Val | `3` | `0` | `0.000000` | `0.228917` |
| `ES|Ourense|Beariz` | Ourense | Beariz | `3` | `0` | `0.000000` | `0.149323` |
| `ES|Ourense|Cualedro` | Ourense | Cualedro | `3` | `0` | `0.000000` | `0.239391` |
| `ES|A Coruña|Oza Cesuras` | A Coruña | Oza Cesuras | `2` | `0` | `0.000000` | `0.448849` |
| `ES|Ourense|Piñor` | Ourense | Piñor | `2` | `0` | `0.000000` | `0.141028` |
| `ES|Ourense|Os Blancos` | Ourense | Os Blancos | `2` | `0` | `0.000000` | `0.135523` |
| `ES|Ourense|Oímbra` | Ourense | Oímbra | `2` | `0` | `0.000000` | `0.458865` |
| `ES|Pontevedra|Catoira` | Pontevedra | Catoira | `2` | `0` | `0.000000` | `0.168170` |
| `ES|Ourense|O Carballiño` | Ourense | O Carballiño | `2` | `0` | `0.000000` | `0.150661` |

## Reading

- The blocked mean, not the single-split number, is what to quote when
  claiming the ranker transfers to unsurveyed ground.
- The spread across folds is the honest error bar. A narrow spread on a
  small holdout is still a small holdout.
- The per-block table is the geographic error surface: a block with many
  positives and low recall is a morphology or landscape the model has
  not learned, not noise.

