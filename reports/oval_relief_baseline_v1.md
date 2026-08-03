# O Val 1 m relief baseline (no training)

`49` vignettes over the O Val holdout: `7` catalogued castros against `42` named
negatives. Channels are `512 m` at `1 m` from PNOA 2024 ground returns.

Descriptor is hand-written, not learned: annular edge (ring `35-95 m` relief
std minus background) weighted twice, plus platform lift (core mean minus
background mean). **It was tuned while looking at these vignettes**, so it is a
ceiling for "simple hand-designed baseline", not an independent result.

## Castro ranks

| rank | site | score |
|---:|---|---:|
| `1` | O Castro (Castro de Quintá) | `+0.8014` |
| `2` | Monte do Castro (Castro de Vilasuso) | `+0.4774` |
| `5` | O Castrillón | `+0.4428` |
| `9` | As Croas | `+0.3621` |
| `12` | Castro da Pedreira | `+0.2974` |
| `18` | Castro de Trasancos | `+0.0993` |
| `36` | Castro de Pena Lopesa | `-0.1098` |

| metric | value |
|---|---:|
| precision@`7` | `0.43` |
| recall in top decile | `0.29` |
| median rank percentile | `0.184` |

## What competes with castros at the top

Ranks `3`, `4`, `6` and `7` are all `natural_landform`: Coto das Penas, Pena
Grande, Monte Painceira, Coto de Vilasuso. Rocky knolls read as platforms with
an edge, which is exactly the descriptor's definition.

This is the false-positive class Landauer et al. (2025) report as surviving at
continental scale, and it is visible here only because the negatives carry
their class. A corpus of mounds alone would have hidden it.

`Mámoa de Rioboo 1` lands at rank `10`, below five of seven castros: the
mound confusion is real but no longer dominant once size is implicitly in play.

## Pena Lopesa, again

Rank `36` of `49`, the only castro below the median. Consistent with every
previous pass of the project. Its prominence is negative (`-9.4 m`), so any
descriptor rewarding an elevated platform must fail on it by construction.
It stays the honest hard case, and no descriptor should be tuned until it
passes — that would be fitting to one site.

## How to read this against the literature

Precision@`7` of `0.43` is above the `0.26` Landauer reports, but the two are
not comparable: this is `49` candidates in one parish with a descriptor tuned
on them, against a blind sweep of `180.000 km2`. The number here is a **floor
for the trained model to beat**, not evidence of anything.
