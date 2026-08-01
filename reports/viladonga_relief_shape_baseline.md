# Viladonga relief shape baseline

Generated: 2026-08-01

- Chip manifest: `data/viladonga-pilot/pnoa_chip_manifest.tsv`
- Relief manifest: `data/viladonga-pilot/lidar_derivatives_manifest.tsv`
- Output TSV: `data/viladonga-pilot/relief_shape_baseline.tsv`
- Baseline: `centered_positive_shape_template_on_relief_grid`
- Rows checked: 9
- OK rows: 9
- Failed rows: 0
- Signal status: `relief_shape_signal_present_in_controlled_chip`

## Positive Row

- Chip: `viladonga-pnoa-positive-1`
- Relief score: 10.517642
- Relief-rank: 1 of 9
- Negative median relief score: -1.302530
- Slope ratio: 1.146870
- LRM abs ratio: 1.173583
- Hillshade edge ratio: 0.778863
- DEM inside delta: 3.150635 m
- LRM inside delta: 0.496445 m

## Signal Reading

Relief shows the strongest controlled-chip signal so far: the known castro ranks first against the eight negatives. This supports moving from PNOA-only inspection toward a relief-led morphology baseline.

## Top Relief Scores

| Rank | Chip | Class | Score | Slope ratio | LRM abs ratio | DEM delta m |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `viladonga-pnoa-positive-1` | 1 | 10.517642 | 1.146870 | 1.173583 | 3.150635 |
| 2 | `viladonga-pnoa-negative-8` | 0 | 3.415820 | 1.028784 | 0.931376 | 0.636230 |
| 3 | `viladonga-pnoa-negative-3` | 0 | 3.281286 | 1.075331 | 1.070182 | 0.509827 |
| 4 | `viladonga-pnoa-negative-5` | 0 | 1.205023 | 0.887253 | 1.120843 | 1.140381 |
| 5 | `viladonga-pnoa-negative-2` | 0 | -0.314429 | 1.002584 | 0.857550 | 0.522705 |

## Interpretation

This is a controlled baseline, not a detector. The positive mask is projected onto the relief grid for Viladonga and reused as a centered template for the negative chips. The score compares slope, absolute LRM, hillshade-edge texture, DEM inside-vs-context elevation and LRM inside-vs-context elevation against the negative median.

The DEM inside-vs-context signal can capture the fact that the known hillfort sits on a topographic high; that is useful hillfort morphology, but not by itself proof of walls or ditches. The wall/ditch question needs finer LiDAR or a richer relief baseline.

The strength of this result depends on the relief source listed in the manifest. It should remain a controlled morphology signal until it is repeated across more known castros and hard negatives.
