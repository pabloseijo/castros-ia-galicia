# Weak-label castro-vs-mamoa specialist v1

Generated: 2026-08-01T00:00:00Z

## What This Is

A specialist ranker for the main false-positive pattern found in the error review batch: castros confused with mamoas/megalithic mounds.
It is trained only on `train` positives plus `train` negatives whose `negative_type` is `megalithic_mound`.
This is an error-analysis layer, not an archaeological detector.

## Files

- Feature table: `data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_features.tsv`
- Score table: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_msrm_full_scores.tsv`
- Metrics table: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_msrm_full_metrics.tsv`
- Model JSON: `data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_msrm_full_model.json`

## Training Setup

- Train dataset: `train`
- Positives: `1844`
- Mamoa negatives: `4972`
- Feature count: `47`
- Final train loss: `0.345199`

## Main Result

- Fusion holdouts: ROC-AUC `0.944312`, AP `0.909383`, P@50 `0.900000`.
- Specialist holdouts: ROC-AUC `0.922362`, AP `0.868727`, P@50 `0.860000`.
- Fusion+specialist mean holdouts: ROC-AUC `0.938581`, AP `0.896198`, P@50 `0.880000`.
- Fusion+specialist mean val: ROC-AUC `0.919941`, AP `0.779531`, P@50 `0.940000`.

## Metrics

| Score | Dataset | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Median pos rank |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fusion_reference | holdouts | all | 204 | 68 | 136 | 0.944312 | 0.909383 | 0.900000 | 0.661765 | 35.5 |
| fusion_reference | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.945931 | 0.912630 | 0.900000 | 0.661765 | 35.5 |
| fusion_reference | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion_reference | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.947917 | 0.907557 | 0.880000 | 0.687500 | 33.5 |
| fusion_reference | test | all | 2383 | 528 | 1855 | 0.925436 | 0.812968 | 1.000000 | 0.094697 | 302.5 |
| fusion_reference | test | castro_vs_mamoa | 1777 | 528 | 1249 | 0.945048 | 0.903738 | 1.000000 | 0.094697 | 272.5 |
| fusion_reference | train | all | 8641 | 1844 | 6797 | 0.932440 | 0.829662 | 1.000000 | 0.027115 | 1036.5 |
| fusion_reference | train | castro_vs_mamoa | 6816 | 1844 | 4972 | 0.945134 | 0.895337 | 1.000000 | 0.027115 | 962.5 |
| fusion_reference | val | all | 1851 | 359 | 1492 | 0.927349 | 0.799049 | 0.960000 | 0.133705 | 200.0 |
| fusion_reference | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.929913 | 0.871839 | 1.000000 | 0.139276 | 185.0 |
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
| fusion_specialist_mean | holdouts | all | 204 | 68 | 136 | 0.938581 | 0.896198 | 0.880000 | 0.647059 | 36.0 |
| fusion_specialist_mean | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.941287 | 0.901285 | 0.880000 | 0.647059 | 36.0 |
| fusion_specialist_mean | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion_specialist_mean | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.943287 | 0.893398 | 0.860000 | 0.671875 | 35.0 |
| fusion_specialist_mean | test | all | 2383 | 528 | 1855 | 0.915003 | 0.782688 | 0.960000 | 0.090909 | 312.5 |
| fusion_specialist_mean | test | castro_vs_mamoa | 1777 | 528 | 1249 | 0.943350 | 0.899763 | 1.000000 | 0.094697 | 273.5 |
| fusion_specialist_mean | train | all | 8641 | 1844 | 6797 | 0.927241 | 0.813215 | 0.980000 | 0.026573 | 1040.0 |
| fusion_specialist_mean | train | castro_vs_mamoa | 6816 | 1844 | 4972 | 0.945412 | 0.897299 | 1.000000 | 0.027115 | 953.0 |
| fusion_specialist_mean | val | all | 1851 | 359 | 1492 | 0.919941 | 0.779531 | 0.940000 | 0.130919 | 209.0 |
| fusion_specialist_mean | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.927627 | 0.869098 | 1.000000 | 0.139276 | 188.0 |
| fusion_specialist_product | holdouts | all | 204 | 68 | 136 | 0.938798 | 0.896403 | 0.880000 | 0.647059 | 36.0 |
| fusion_specialist_product | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.941398 | 0.901363 | 0.900000 | 0.661765 | 36.0 |
| fusion_specialist_product | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion_specialist_product | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.943056 | 0.893429 | 0.860000 | 0.671875 | 34.5 |
| fusion_specialist_product | test | all | 2383 | 528 | 1855 | 0.914830 | 0.782128 | 0.960000 | 0.090909 | 312.5 |
| fusion_specialist_product | test | castro_vs_mamoa | 1777 | 528 | 1249 | 0.942662 | 0.898505 | 1.000000 | 0.094697 | 273.5 |
| fusion_specialist_product | train | all | 8641 | 1844 | 6797 | 0.926426 | 0.812786 | 0.980000 | 0.026573 | 1041.5 |
| fusion_specialist_product | train | castro_vs_mamoa | 6816 | 1844 | 4972 | 0.944121 | 0.896161 | 1.000000 | 0.027115 | 952.5 |
| fusion_specialist_product | val | all | 1851 | 359 | 1492 | 0.919261 | 0.779017 | 0.940000 | 0.130919 | 210.0 |
| fusion_specialist_product | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.926357 | 0.867848 | 1.000000 | 0.139276 | 189.0 |
| fusion70_specialist30 | holdouts | all | 204 | 68 | 136 | 0.944096 | 0.905737 | 0.900000 | 0.661765 | 35.5 |
| fusion70_specialist30 | holdouts | castro_vs_mamoa | 201 | 68 | 133 | 0.946263 | 0.910028 | 0.900000 | 0.661765 | 35.5 |
| fusion70_specialist30 | holdouts | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 2.5 |
| fusion70_specialist30 | holdouts | split:test_trasancos | 199 | 64 | 135 | 0.948264 | 0.903635 | 0.860000 | 0.671875 | 33.5 |
| fusion70_specialist30 | test | all | 2383 | 528 | 1855 | 0.920814 | 0.796907 | 0.960000 | 0.090909 | 311.5 |
| fusion70_specialist30 | test | castro_vs_mamoa | 1777 | 528 | 1249 | 0.945493 | 0.903755 | 1.000000 | 0.094697 | 274.5 |
| fusion70_specialist30 | train | all | 8641 | 1844 | 6797 | 0.930733 | 0.822780 | 1.000000 | 0.027115 | 1034.0 |
| fusion70_specialist30 | train | castro_vs_mamoa | 6816 | 1844 | 4972 | 0.946610 | 0.899179 | 1.000000 | 0.027115 | 953.5 |
| fusion70_specialist30 | val | all | 1851 | 359 | 1492 | 0.924113 | 0.789181 | 0.940000 | 0.130919 | 209.0 |
| fusion70_specialist30 | val | castro_vs_mamoa | 1357 | 359 | 998 | 0.929798 | 0.872558 | 1.000000 | 0.139276 | 190.0 |

## O Val Reading

| Fusion rank | Specialist rank | Mean rank | Product rank | Max-safety rank | Class | Fusion | Specialist | Name |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 4 | 27 | 12 | 12 | 12 | 1 | 0.99291529 | 0.93221491 | `O Castro (Castro de Quintá)` |
| 16 | 31 | 24 | 24 | 22 | 1 | 0.95201300 | 0.85993565 | `Monte do Castro (Castro de Vilasuso)` |
| 24 | 16 | 19 | 19 | 24 | 1 | 0.91701271 | 0.96556792 | `Castro da Pedreira` |
| 110 | 126 | 120 | 120 | 120 | 0 | 0.14298555 | 0.13161160 | `Mámoa do Val/Mámoa de Santa Margarida` |
| 131 | 156 | 146 | 142 | 61 | 1 | 0.07690272 | 0.06225647 | `Castro de Pena Lopesa` |

## Interpretation

- The specialist improves the explicit castro-vs-mamoa bottleneck and supports treating mamoas as a separate hard-negative family.
- For `Castro de Pena Lopesa`, ranks are fusion `131`, specialist `156`, mean `146` and max-safety `61`.
- The product score still inherits the low fusion score for Pena Lopesa, so the project should keep three lanes: main fusion, morphology safety, and mamoa specialist.
- This layer should inform QGIS review, hard-negative mining and the next full review queue.
