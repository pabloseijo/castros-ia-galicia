# Viladonga radial relief profile

Generated: 2026-08-01

- Chip manifest: `data/viladonga-pilot/pnoa_chip_manifest.tsv`
- Relief manifest: `data/viladonga-pilot/lidar_derivatives_manifest.tsv`
- Summary TSV: `data/viladonga-pilot/radial_relief_summary.tsv`
- Rings TSV: `data/viladonga-pilot/radial_relief_rings.tsv`
- Baseline: `normalized_radial_rings_on_relief_grid`
- Rows checked: 9
- OK rows: 9
- Failed rows: 0
- Signal status: `radial_edge_and_topography_signal_present`

## Positive Summary

- Chip: `viladonga-pnoa-positive-1`
- Edge/talud score: 10.979821
- Edge/talud rank: 1 of 9
- Topographic prominence rank: 1 of 9
- Edge slope ring: `expected_wall_inner` (22.411860 vs context 16.248982, ratio 1.379278)
- Edge LRM ring: `expected_wall_inner` (1.576953 vs context 0.856715, ratio 1.840696)
- Edge hillshade ring: `expected_wall_outer` (0.502716 vs context 0.577402, ratio 0.870652)
- DEM prominence core-vs-far-context: 13.205688 m
- Equivalent radius: 63.82 m

## Positive Rings

| Ring | Pixels | DEM | Slope | LRM abs | Hillshade edge |
|---|---:|---:|---:|---:|---:|
| `core` | 4606 | 547.912964 | 8.399146 | 0.602887 | 0.282128 |
| `inner_plateau` | 4518 | 548.656677 | 21.293791 | 1.870442 | 0.598223 |
| `expected_wall_inner` | 4860 | 545.698181 | 22.411860 | 1.576953 | 0.474356 |
| `expected_wall_outer` | 7491 | 544.643188 | 14.060316 | 1.063816 | 0.502716 |
| `near_exterior` | 15307 | 542.149414 | 16.213928 | 0.878113 | 0.574783 |
| `far_context` | 42758 | 534.707275 | 16.284037 | 0.835318 | 0.580021 |

## Edge/Talud Ranking

| Rank | Chip | Class | Score | Slope ratio | LRM abs ratio | Hillshade ratio |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `viladonga-pnoa-positive-1` | 1 | 10.979821 | 1.379278 | 1.840696 | 0.870652 |
| 2 | `viladonga-pnoa-negative-8` | 0 | 4.446190 | 0.898896 | 0.661020 | 1.015477 |
| 3 | `viladonga-pnoa-negative-2` | 0 | 1.975847 | 0.875232 | 0.726549 | 0.793969 |
| 4 | `viladonga-pnoa-negative-6` | 0 | 0.808630 | 0.760066 | 0.977316 | 0.784740 |
| 5 | `viladonga-pnoa-negative-4` | 0 | 0.143460 | 0.768037 | 0.779774 | 0.823408 |

## Topographic Prominence Ranking

| Rank | Chip | Class | DEM prominence m |
|---:|---|---:|---:|
| 1 | `viladonga-pnoa-positive-1` | 1 | 13.205688 |
| 2 | `viladonga-pnoa-negative-2` | 0 | 4.796997 |
| 3 | `viladonga-pnoa-negative-5` | 0 | 4.194000 |
| 4 | `viladonga-pnoa-negative-8` | 0 | 2.565277 |
| 5 | `viladonga-pnoa-negative-3` | 0 | 1.947449 |

## Interpretation

The known castro ranks first both in topographic prominence and in the radial edge/talud score. This is the strongest current evidence that the relief signal is not only generic elevation: there is also ring-local contrast around the expected boundary.

This is still a controlled smoke test over the relief source listed in the manifest. The result should guide the next measurement, not serve as a claim of automatic archaeological detection. More known castros and hard negatives are still required.
