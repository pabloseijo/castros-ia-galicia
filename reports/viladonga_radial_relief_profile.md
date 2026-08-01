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
- Edge/talud score: 13.172684
- Edge/talud rank: 1 of 9
- Topographic prominence rank: 1 of 9
- Edge slope ring: `expected_wall_inner` (13.781946 vs context 11.768352, ratio 1.171102)
- Edge LRM ring: `expected_wall_inner` (0.999454 vs context 0.638250, ratio 1.565929)
- Edge hillshade ring: `expected_wall_inner` (0.519447 vs context 0.247029, ratio 2.102781)
- DEM prominence core-vs-far-context: 13.609314 m
- Equivalent radius: 64.27 m

## Positive Rings

| Ring | Pixels | DEM | Slope | LRM abs | Hillshade edge |
|---|---:|---:|---:|---:|---:|
| `core` | 187 | 547.978638 | 5.515691 | 0.541654 | 0.288594 |
| `inner_plateau` | 188 | 548.526611 | 11.693231 | 1.587700 | 0.657698 |
| `expected_wall_inner` | 197 | 545.751282 | 13.781946 | 0.999454 | 0.519447 |
| `expected_wall_outer` | 305 | 544.603271 | 6.614532 | 0.861699 | 0.329690 |
| `near_exterior` | 624 | 541.645813 | 10.790936 | 0.604459 | 0.241769 |
| `far_context` | 1741 | 534.369324 | 12.745768 | 0.672041 | 0.252289 |

## Edge/Talud Ranking

| Rank | Chip | Class | Score | Slope ratio | LRM abs ratio | Hillshade ratio |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `viladonga-pnoa-positive-1` | 1 | 13.172684 | 1.171102 | 1.565929 | 2.102781 |
| 2 | `viladonga-pnoa-negative-4` | 0 | 2.423540 | 0.867145 | 0.966250 | 1.028554 |
| 3 | `viladonga-pnoa-negative-6` | 0 | 1.819809 | 0.767715 | 1.014676 | 1.021001 |
| 4 | `viladonga-pnoa-negative-2` | 0 | 0.111900 | 0.904705 | 0.836716 | 0.941915 |
| 5 | `viladonga-pnoa-negative-7` | 0 | 0.105993 | 0.838712 | 0.959287 | 0.901464 |

## Topographic Prominence Ranking

| Rank | Chip | Class | DEM prominence m |
|---:|---|---:|---:|
| 1 | `viladonga-pnoa-positive-1` | 1 | 13.609314 |
| 2 | `viladonga-pnoa-negative-2` | 0 | 5.013977 |
| 3 | `viladonga-pnoa-negative-5` | 0 | 4.464478 |
| 4 | `viladonga-pnoa-negative-8` | 0 | 2.737549 |
| 5 | `viladonga-pnoa-negative-3` | 0 | 2.145203 |

## Interpretation

The known castro ranks first both in topographic prominence and in the radial edge/talud score. This is the strongest current evidence that the relief signal is not only generic elevation: there is also ring-local contrast around the expected boundary.

This is still a controlled smoke test over a 5 m MDT WCS product. The result should guide the next measurement, not serve as a claim of automatic archaeological detection. Fine LiDAR and more known castros are still required.
