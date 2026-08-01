# Weak-label castro-vs-mamoa specialist v1

Generated: 2026-08-01T00:00:00Z

## What This Is

A specialist ranker for the main false-positive pattern found in the error review batch: castros confused with mamoas/megalithic mounds.
It is trained only on `train` positives plus `train` negatives whose `negative_type` is `megalithic_mound`.
This is an error-analysis layer, not an archaeological detector.

## Files

- Feature table: `data/weak-label-fusion-v1/weak_label_rgb_relief_full_features.tsv`
- Score table: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_full_scores.tsv`
- Metrics table: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_full_metrics.tsv`
- Model JSON: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_full_model.json`

## Training Setup

- Train dataset: `train`
- Positives: `1844`
- Mamoa negatives: `4972`
- Feature count: `47`
- Final train loss: `0.345199`

## Main Result

- Fusion holdouts: ROC-AUC `0.925281`, AP `0.880837`, P@50 `0.880000`.
- Specialist holdouts: ROC-AUC `0.922362`, AP `0.868727`, P@50 `0.860000`.
- Fusion+specialist mean holdouts: ROC-AUC `0.926146`, AP `0.879864`, P@50 `0.860000`.
- Fusion+specialist mean val: ROC-AUC `0.905014`, AP `0.755024`, P@50 `0.940000`.

## Metrics

| Score | Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Median pos rank |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fusion_reference | holdouts | all | 204 | 68 | 136 | 0.925281 | 0.880837 | 0.880000 | 0.647059 | 36.5 |
| fusion_reference | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.926913 | 0.883990 | 0.880000 | 0.647059 | 36.5 |
| fusion_reference | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion_reference | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.935764 | 0.879315 | 0.840000 | 0.656250 | 34.5 |
| fusion_reference | test | all | 2383 | 528 | 1855 | 0.910299 | 0.774873 | 0.940000 | 0.089015 | 312.5 |
| fusion_reference | test | castro_vs_mamoa | 1777 | 528 | 1249 | 0.930784 | 0.881468 | 1.000000 | 0.094697 | 274.5 |
| fusion_reference | train | all | 8641 | 1844 | 6797 | 0.916019 | 0.793529 | 1.000000 | 0.027115 | 1057.5 |
| fusion_reference | train | castro_vs_mamoa | 6816 | 1844 | 4972 | 0.930043 | 0.875294 | 1.000000 | 0.027115 | 959.5 |
| fusion_reference | val | all | 1851 | 359 | 1492 | 0.905931 | 0.759620 | 0.940000 | 0.130919 | 206.0 |
| fusion_reference | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.902406 | 0.829138 | 1.000000 | 0.139276 | 191.0 |
| castro_mamoa_specialist | holdouts | all | 204 | 68 | 136 | 0.922362 | 0.868727 | 0.860000 | 0.632353 | 38.0 |
| castro_mamoa_specialist | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.924923 | 0.873656 | 0.860000 | 0.632353 | 38.0 |
| castro_mamoa_specialist | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| castro_mamoa_specialist | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.927546 | 0.865037 | 0.820000 | 0.640625 | 36.5 |
| castro_mamoa_specialist | test | all | 2383 | 528 | 1855 | 0.890131 | 0.727865 | 0.920000 | 0.087121 | 342.0 |
| castro_mamoa_specialist | test | castro_vs_mamoa | 1777 | 528 | 1249 | 0.929348 | 0.878478 | 1.000000 | 0.094697 | 276.5 |
| castro_mamoa_specialist | train | all | 8641 | 1844 | 6797 | 0.909099 | 0.767365 | 0.960000 | 0.026030 | 1096.5 |
| castro_mamoa_specialist | train | castro_vs_mamoa | 6816 | 1844 | 4972 | 0.934318 | 0.878883 | 1.000000 | 0.027115 | 962.5 |
| castro_mamoa_specialist | val | all | 1851 | 359 | 1492 | 0.899621 | 0.733719 | 0.900000 | 0.125348 | 217.0 |
| castro_mamoa_specialist | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.912516 | 0.845939 | 1.000000 | 0.139276 | 190.0 |
| fusion_specialist_mean | holdouts | all | 204 | 68 | 136 | 0.926146 | 0.879864 | 0.860000 | 0.632353 | 36.5 |
| fusion_specialist_mean | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.928019 | 0.883485 | 0.860000 | 0.632353 | 36.5 |
| fusion_specialist_mean | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion_specialist_mean | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.933796 | 0.877616 | 0.840000 | 0.656250 | 34.5 |
| fusion_specialist_mean | test | all | 2383 | 528 | 1855 | 0.902189 | 0.758393 | 0.940000 | 0.089015 | 318.5 |
| fusion_specialist_mean | test | castro_vs_mamoa | 1777 | 528 | 1249 | 0.931242 | 0.881923 | 1.000000 | 0.094697 | 274.5 |
| fusion_specialist_mean | train | all | 8641 | 1844 | 6797 | 0.914456 | 0.785570 | 0.980000 | 0.026573 | 1065.0 |
| fusion_specialist_mean | train | castro_vs_mamoa | 6816 | 1844 | 4972 | 0.933860 | 0.879141 | 1.000000 | 0.027115 | 959.0 |
| fusion_specialist_mean | val | all | 1851 | 359 | 1492 | 0.905014 | 0.755024 | 0.940000 | 0.130919 | 210.0 |
| fusion_specialist_mean | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.909596 | 0.839961 | 1.000000 | 0.139276 | 192.0 |
| fusion_specialist_product | holdouts | all | 204 | 68 | 136 | 0.925606 | 0.879808 | 0.860000 | 0.632353 | 36.5 |
| fusion_specialist_product | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.927466 | 0.883413 | 0.860000 | 0.632353 | 36.5 |
| fusion_specialist_product | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion_specialist_product | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.933681 | 0.877705 | 0.840000 | 0.656250 | 34.5 |
| fusion_specialist_product | test | all | 2383 | 528 | 1855 | 0.902905 | 0.759623 | 0.940000 | 0.089015 | 318.5 |
| fusion_specialist_product | test | castro_vs_mamoa | 1777 | 528 | 1249 | 0.931039 | 0.881802 | 1.000000 | 0.094697 | 274.5 |
| fusion_specialist_product | train | all | 8641 | 1844 | 6797 | 0.914328 | 0.785935 | 0.980000 | 0.026573 | 1065.5 |
| fusion_specialist_product | train | castro_vs_mamoa | 6816 | 1844 | 4972 | 0.933278 | 0.878704 | 1.000000 | 0.027115 | 959.5 |
| fusion_specialist_product | val | all | 1851 | 359 | 1492 | 0.905214 | 0.755677 | 0.940000 | 0.130919 | 210.0 |
| fusion_specialist_product | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.908940 | 0.839066 | 1.000000 | 0.139276 | 192.0 |
| fusion70_specialist30 | holdouts | all | 204 | 68 | 136 | 0.925389 | 0.878952 | 0.860000 | 0.632353 | 36.5 |
| fusion70_specialist30 | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.927355 | 0.882701 | 0.860000 | 0.632353 | 36.5 |
| fusion70_specialist30 | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion70_specialist30 | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.934028 | 0.876814 | 0.840000 | 0.656250 | 34.5 |
| fusion70_specialist30 | test | all | 2383 | 528 | 1855 | 0.905936 | 0.766130 | 0.940000 | 0.089015 | 316.5 |
| fusion70_specialist30 | test | castro_vs_mamoa | 1777 | 528 | 1249 | 0.931500 | 0.882249 | 1.000000 | 0.094697 | 275.0 |
| fusion70_specialist30 | train | all | 8641 | 1844 | 6797 | 0.915559 | 0.789634 | 0.980000 | 0.026573 | 1061.5 |
| fusion70_specialist30 | train | castro_vs_mamoa | 6816 | 1844 | 4972 | 0.932792 | 0.878061 | 1.000000 | 0.027115 | 956.5 |
| fusion70_specialist30 | val | all | 1851 | 359 | 1492 | 0.906058 | 0.758570 | 0.940000 | 0.130919 | 206.0 |
| fusion70_specialist30 | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.907439 | 0.836417 | 1.000000 | 0.139276 | 191.0 |

## O Val Reading

| Fusion rank | Specialist rank | Mean rank | Product rank | Max-safety rank | Class | Fusion | Specialist | Name |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 16 | 27 | 19 | 19 | 13 | 1 | 0.93484924 | 0.93221491 | `O Castro (Castro de Quintá)` |
| 17 | 16 | 16 | 16 | 22 | 1 | 0.92970190 | 0.96556792 | `Castro da Pedreira` |
| 33 | 31 | 32 | 32 | 46 | 1 | 0.78639438 | 0.85993565 | `Monte do Castro (Castro de Vilasuso)` |
| 114 | 126 | 123 | 122 | 122 | 0 | 0.13950332 | 0.13161160 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 201 | 156 | 176 | 180 | 55 | 1 | 0.01961880 | 0.06225647 | `Castro de Pena Lopesa` |

## Interpretation

- The specialist improves the explicit castro-vs-mamoa bottleneck and supports treating mamoas as a separate hard-negative family.
- For `Castro de Pena Lopesa`, ranks are fusion `201`, specialist `156`, mean `176` and max-safety `55`.
- The product score still inherits the low fusion score for Pena Lopesa, so the project should keep three lanes: main fusion, morphology safety, and mamoa specialist.
- This layer should inform QGIS review, hard-negative mining and the next full review queue.
