# Weak-label castro-vs-mamoa specialist v1

Generated: 2026-08-01T00:00:00Z

## What This Is

A specialist ranker for the main false-positive pattern found in the error review batch: castros confused with mamoas/megalithic mounds.
It is trained only on `train_mini` positives plus `train_mini` negatives whose `negative_type` is `megalithic_mound`.
This is an error-analysis layer, not an archaeological detector.

## Files

- Feature table: `data/weak-label-fusion-v1/weak_label_rgb_relief_features.tsv`
- Score table: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_scores.tsv`
- Metrics table: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_metrics.tsv`
- Model JSON: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_model.json`

## Training Setup

- Train dataset: `train_mini`
- Positives: `276`
- Mamoa negatives: `148`
- Feature count: `47`
- Final train loss: `0.393571`

## Main Result

- Fusion holdouts: ROC-AUC `0.888949`, AP `0.866398`, P@50 `0.900000`.
- Specialist holdouts: ROC-AUC `0.920631`, AP `0.870753`, P@50 `0.880000`.
- Fusion+specialist mean holdouts: ROC-AUC `0.923227`, AP `0.887287`, P@50 `0.900000`.
- Fusion+specialist mean val: ROC-AUC `0.893116`, AP `0.773066`, P@50 `0.980000`.

## Metrics

| Score | Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Median pos rank |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fusion_reference | holdouts | all | 204 | 68 | 136 | 0.888949 | 0.866398 | 0.900000 | 0.661765 | 37.5 |
| fusion_reference | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.888877 | 0.867749 | 0.900000 | 0.661765 | 37.5 |
| fusion_reference | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion_reference | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.897569 | 0.864284 | 0.880000 | 0.687500 | 36.5 |
| fusion_reference | train_mini | all | 553 | 276 | 277 | 0.869330 | 0.859469 | 0.920000 | 0.166667 | 156.5 |
| fusion_reference | train_mini | castro_vs_mamoa | 424 | 276 | 148 | 0.896641 | 0.947133 | 0.980000 | 0.177536 | 140.5 |
| fusion_reference | val | all | 1851 | 359 | 1492 | 0.878253 | 0.754336 | 0.980000 | 0.136490 | 207.0 |
| fusion_reference | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.853716 | 0.783233 | 1.000000 | 0.139276 | 200.0 |
| castro_mamoa_specialist | holdouts | all | 204 | 68 | 136 | 0.920631 | 0.870753 | 0.880000 | 0.647059 | 36.5 |
| castro_mamoa_specialist | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.923264 | 0.876547 | 0.880000 | 0.647059 | 36.5 |
| castro_mamoa_specialist | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 2.5 |
| castro_mamoa_specialist | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.916204 | 0.857389 | 0.820000 | 0.640625 | 34.5 |
| castro_mamoa_specialist | train_mini | all | 553 | 276 | 277 | 0.841221 | 0.799532 | 0.840000 | 0.152174 | 165.5 |
| castro_mamoa_specialist | train_mini | castro_vs_mamoa | 424 | 276 | 148 | 0.913362 | 0.955823 | 1.000000 | 0.181159 | 140.5 |
| castro_mamoa_specialist | val | all | 1851 | 359 | 1492 | 0.892655 | 0.742794 | 0.900000 | 0.125348 | 211.0 |
| castro_mamoa_specialist | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.892278 | 0.814476 | 0.980000 | 0.136490 | 193.0 |
| fusion_specialist_mean | holdouts | all | 204 | 68 | 136 | 0.923227 | 0.887287 | 0.900000 | 0.661765 | 35.5 |
| fusion_specialist_mean | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.924701 | 0.890485 | 0.900000 | 0.661765 | 35.5 |
| fusion_specialist_mean | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 2.5 |
| fusion_specialist_mean | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.919329 | 0.876879 | 0.860000 | 0.671875 | 33.5 |
| fusion_specialist_mean | train_mini | all | 553 | 276 | 277 | 0.862973 | 0.849400 | 0.880000 | 0.159420 | 157.5 |
| fusion_specialist_mean | train_mini | castro_vs_mamoa | 424 | 276 | 148 | 0.911477 | 0.953970 | 0.980000 | 0.177536 | 140.5 |
| fusion_specialist_mean | val | all | 1851 | 359 | 1492 | 0.893116 | 0.773066 | 0.980000 | 0.136490 | 200.0 |
| fusion_specialist_mean | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.881624 | 0.815519 | 0.980000 | 0.136490 | 191.0 |
| fusion_specialist_product | holdouts | all | 204 | 68 | 136 | 0.921713 | 0.884400 | 0.900000 | 0.661765 | 35.5 |
| fusion_specialist_product | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.922822 | 0.886932 | 0.900000 | 0.661765 | 35.5 |
| fusion_specialist_product | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion_specialist_product | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.921065 | 0.878650 | 0.860000 | 0.671875 | 33.5 |
| fusion_specialist_product | train_mini | all | 553 | 276 | 277 | 0.863745 | 0.850844 | 0.880000 | 0.159420 | 157.5 |
| fusion_specialist_product | train_mini | castro_vs_mamoa | 424 | 276 | 148 | 0.910130 | 0.953441 | 0.980000 | 0.177536 | 140.5 |
| fusion_specialist_product | val | all | 1851 | 359 | 1492 | 0.892353 | 0.773065 | 0.960000 | 0.133705 | 199.0 |
| fusion_specialist_product | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.879885 | 0.813763 | 0.980000 | 0.136490 | 190.0 |
| fusion70_specialist30 | holdouts | all | 204 | 68 | 136 | 0.917712 | 0.885894 | 0.880000 | 0.647059 | 36.0 |
| fusion70_specialist30 | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.918399 | 0.887906 | 0.880000 | 0.647059 | 36.0 |
| fusion70_specialist30 | holdouts | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 2.5 |
| fusion70_specialist30 | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.915046 | 0.878399 | 0.840000 | 0.656250 | 34.5 |
| fusion70_specialist30 | train_mini | all | 553 | 276 | 277 | 0.867407 | 0.854743 | 0.880000 | 0.159420 | 156.0 |
| fusion70_specialist30 | train_mini | castro_vs_mamoa | 424 | 276 | 148 | 0.907241 | 0.951991 | 0.980000 | 0.177536 | 140.5 |
| fusion70_specialist30 | val | all | 1851 | 359 | 1492 | 0.889352 | 0.769327 | 0.980000 | 0.136490 | 199.0 |
| fusion70_specialist30 | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.873072 | 0.805647 | 0.980000 | 0.136490 | 192.0 |

## O Val Reading

| Fusion rank | Specialist rank | Mean rank | Product rank | Max-safety rank | Class | Fusion | Specialist | Name |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 14 | 30 | 18 | 17 | 14 | 1 | 0.87463272 | 0.87274376 | `O Castro (Castro de Quintá)` |
| 26 | 25 | 24 | 23 | 30 | 1 | 0.73214328 | 0.92073759 | `Castro da Pedreira` |
| 32 | 33 | 30 | 29 | 35 | 1 | 0.64752202 | 0.85172540 | `Monte do Castro (Castro de Vilasuso)` |
| 80 | 95 | 90 | 89 | 99 | 0 | 0.32277415 | 0.25713143 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 199 | 2 | 51 | 95 | 72 | 1 | 0.06230073 | 1.00000000 | `Castro de Pena Lopesa` |

## Interpretation

- The specialist improves the explicit castro-vs-mamoa bottleneck and supports treating mamoas as a separate hard-negative family.
- It ranks `Castro de Pena Lopesa` very high by specialist probability, which confirms that the fusion failure is not simple absence of signal.
- The product score still inherits the low fusion score for Pena Lopesa, so the project should keep three lanes: main fusion, morphology safety, and mamoa specialist.
- This layer should inform QGIS review and hard-negative mining before exporting full `test/train`.
