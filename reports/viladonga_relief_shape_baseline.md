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
- Relief score: 15.416635
- Relief-rank: 1 of 9
- Negative median relief score: -1.140906
- Slope ratio: 1.016721
- LRM abs ratio: 1.340616
- Hillshade edge ratio: 1.879517
- DEM inside delta: 9.266235 m
- LRM inside delta: 0.130844 m

## Signal Reading

Relief shows the strongest controlled-chip signal so far: the known castro ranks first against the eight negatives. This supports moving from PNOA-only inspection toward a relief-led morphology baseline.

## Top Relief Scores

| Rank | Chip | Class | Score | Slope ratio | LRM abs ratio | DEM delta m |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `viladonga-pnoa-positive-1` | 1 | 15.416635 | 1.016721 | 1.340616 | 9.266235 |
| 2 | `viladonga-pnoa-negative-2` | 0 | 3.282035 | 0.894849 | 0.846503 | 2.784607 |
| 3 | `viladonga-pnoa-negative-5` | 0 | 2.629459 | 0.867133 | 0.866700 | 3.435822 |
| 4 | `viladonga-pnoa-negative-4` | 0 | -0.762525 | 0.766911 | 0.903181 | -6.422729 |
| 5 | `viladonga-pnoa-negative-6` | 0 | -0.787617 | 0.584399 | 0.933290 | -2.311829 |

## Interpretation

This is a controlled baseline, not a detector. The positive mask is projected onto the relief grid for Viladonga and reused as a centered template for the negative chips. The score compares slope, absolute LRM, hillshade-edge texture, DEM inside-vs-context elevation and LRM inside-vs-context elevation against the negative median.

The DEM inside-vs-context signal can capture the fact that the known hillfort sits on a topographic high; that is useful hillfort morphology, but not by itself proof of walls or ditches. The wall/ditch question needs finer LiDAR or a richer relief baseline.

Because the input is a 5 m MDT WCS product, a positive result is only a coarse morphology signal. The fine archaeological test still depends on getting the correct LAZ tiles or an equivalent high-resolution LiDAR/DTM covering Viladonga.
