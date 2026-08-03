# Does 1 m LiDAR separate castros from mámoas?

Sites: `20` castros vs `20` mámoas from the Trasancos holdout.
LiDAR: CNIG PNOA 3rd coverage, 1 m grid from ground returns.

Separation is the absolute gap between class medians, in pooled standard
deviations. Higher is better; the same sites are measured both ways.

| feature | MDT5 (5 m) | LiDAR (1 m) | change |
|---|---:|---:|---:|
| `best_ring_coverage` | `1.15` | `0.90` | `-0.25` |
| `msrm_core_delta` | `1.05` | `0.38` | `-0.67` |
| `msrm_abs_ratio` | `0.21` | `0.53` | `+0.33` |
| `best_ring_balance` | `0.15` | `0.60` | `+0.45` |
| `dominant_scale_ratio` | `0.40` | `0.54` | `+0.15` |

## Verdict

- **LiDAR helps**: `3` of `5` features separate the classes better at 1 m. Finer relief is a real route out of the mámoa problem.

- sites successfully processed: `40` of `40`
- Caveat: ground-return DEMs under dense canopy are themselves interpolated,
  so 1 m nominal resolution is not 1 m of real information everywhere.

