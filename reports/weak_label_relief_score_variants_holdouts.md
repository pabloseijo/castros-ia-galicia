# Weak-label relief score variants

Generated: 2026-08-01T00:00:00Z

## What This Is

A diagnostic comparison of simple relief scoring variants for variable castro morphologies. It reuses the same MDT5 features and does not download new data.
This is model-formulation evidence, not final validation: the variants were inspected after the first single-score baseline and must be confirmed on broader train/val splits.

## Files

- Score TSV: `data/weak-label-relief-v1/weak_label_relief_score_variants_holdouts.tsv`
- Metrics TSV: `data/weak-label-relief-v1/weak_label_relief_score_variant_metrics_holdouts.tsv`

## Variant Logic

- `hilltop`: favors positive topographic prominence plus slope/local-relief contrast.
- `edge_ring`: favors ring/edge contrast without requiring the core to be higher than context.
- `promontory`: favors strong annular relief and edge texture, useful for coastal/promontory shapes.
- `archetype_max`: takes the strongest of the three morphology variants per site.

## Best Overall

- Best all-subset variant: `archetype_max` with ROC-AUC `0.784926` and AP `0.699085`.
- Best O Val variant: `promontory` with ROC-AUC `1.000000` and AP `1.000000`.
- O Val has only five holdout rows, so its perfect score is qualitative error-analysis evidence, not statistical proof.

## Best Variant Counts

- edge_ring: 69
- hilltop: 70
- promontory: 65

## Single Relief Baseline Reference

- single relief all: ROC-AUC `0.730536`, AP `0.636385`.
- single relief split:test_o_val: ROC-AUC `0.750000`, AP `0.950000`.
- single relief split:test_trasancos: ROC-AUC `0.732523`, AP `0.627894`.

## Metrics

| Variant | Subset | Rows | Pos | Neg | ROC-AUC | AP | P@50 | R@50 | Best pos rank | Median pos rank |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| hilltop | all | 204 | 68 | 136 | 0.707829 | 0.655732 | 0.580000 | 0.426471 | 1 | 59.5 |
| hilltop | split:test_o_val | 5 | 4 | 1 | 0.750000 | 0.950000 | 0.800000 | 1.000000 | 1 | 2.5 |
| hilltop | split:test_trasancos | 199 | 64 | 135 | 0.707870 | 0.644048 | 0.580000 | 0.453125 | 1 | 57.5 |
| edge_ring | all | 204 | 68 | 136 | 0.753136 | 0.645811 | 0.620000 | 0.455882 | 1 | 62.0 |
| edge_ring | split:test_o_val | 5 | 4 | 1 | 0.500000 | 0.887500 | 0.800000 | 1.000000 | 1 | 3.0 |
| edge_ring | split:test_trasancos | 199 | 64 | 135 | 0.754051 | 0.634956 | 0.580000 | 0.453125 | 1 | 60.0 |
| promontory | all | 204 | 68 | 136 | 0.646518 | 0.552698 | 0.520000 | 0.382353 | 1 | 73.5 |
| promontory | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| promontory | split:test_trasancos | 199 | 64 | 135 | 0.639005 | 0.539088 | 0.500000 | 0.390625 | 1 | 76.0 |
| archetype_max | all | 204 | 68 | 136 | 0.784926 | 0.699085 | 0.660000 | 0.485294 | 1 | 54.0 |
| archetype_max | split:test_o_val | 5 | 4 | 1 | 1.000000 | 1.000000 | 0.800000 | 1.000000 | 1 | 2.5 |
| archetype_max | split:test_trasancos | 199 | 64 | 135 | 0.777199 | 0.679390 | 0.620000 | 0.484375 | 1 | 54.5 |

## O Val Archetype-Max Reading

| Archetype rank | Best variant | Hilltop rank | Edge-ring rank | Promontory rank | Class | Name |
|---:|---|---:|---:|---:|---:|---|
| 10 | edge_ring | 27 | 9 | 124 | 1 | `O Castro (Castro de Quintá)` |
| 21 | promontory | 203 | 56 | 11 | 1 | `Castro de Pena Lopesa` |
| 29 | hilltop | 15 | 146 | 63 | 1 | `Castro da Pedreira` |
| 86 | promontory | 66 | 46 | 52 | 1 | `Monte do Castro (Castro de Vilasuso)` |
| 92 | edge_ring | 149 | 48 | 132 | 0 | `Mámoa do Val/Mámoa de Santa Margarida` |

## Interpretation

- A single prominence-heavy relief score misses some plausible castro morphologies, especially coastal/promontory cases.
- The multi-variant score rescues `Castro de Pena Lopesa` because it no longer assumes that every castro is a raised hilltop.
- This supports the project decision to train or rank with morphology-aware channels rather than one universal castro shape.
- The next validation step is to run these variants over larger train/validation relief exports before treating them as detector features.
