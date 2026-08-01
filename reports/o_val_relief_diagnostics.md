# O Val relief diagnostics

Generated: 2026-08-01T00:00:00Z

## What This Is

A visual diagnostic sheet for the five O Val holdouts, combining PNOA RGB, MDT5 elevation, slope and local relief with the same 120 m reference radius used by the baseline.
This is for error analysis only; it is not a detector and it does not create new archaeological claims.

## Contact Sheet

![O Val relief diagnostics](reports/figures/o_val_relief_diagnostics/o_val_contact_sheet.png)

## Rows

| Relief rank | RGB rank | Class | Name | Prominence m | Slope ratio | LRM abs ratio | Watchlist |
|---:|---:|---:|---|---:|---:|---:|---|
| 10 | 78 | 1 | `O Castro (Castro de Quintá)` | 7.64156342 | 2.02364198 | 1.64714834 |  |
| 59 | 34 | 1 | `Castro da Pedreira` | 26.71990967 | 1.04493877 | 0.72819347 |  |
| 64 | 68 | 1 | `Monte do Castro (Castro de Vilasuso)` | 9.87294006 | 1.07184991 | 0.92996351 |  |
| 88 | 116 | 0 | `Mámoa do Val/Mámoa de Santa Margarida` | 3.83102417 | 0.98847478 | 1.12754807 |  |
| 166 | 204 | 1 | `Castro de Pena Lopesa` | -12.70476627 | 1.01139859 | 1.05024714 | positive_low_relief_rank,positive_low_rgb_rank |

## Reading

- `O Castro (Castro de Quintá)` is the clearest O Val relief hit: high global relief rank and high slope contrast.
- `Castro da Pedreira` and `Monte do Castro (Castro de Vilasuso)` remain positive but middle-ranked; both need richer LiDAR derivatives before using them as strong detector examples.
- `Castro de Pena Lopesa` is now explicitly on the watchlist because both RGB and MDT5 relief rank it low; this may be a centering, visibility, morphology or source-resolution issue.
- `Mámoa do Val/Mámoa de Santa Margarida` behaves as a useful hard negative because it receives a non-trivial relief score while not being a castro label.
