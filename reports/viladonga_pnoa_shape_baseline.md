# Viladonga PNOA shape baseline

Generated: 2026-08-01

- Manifest: `data/viladonga-pilot/pnoa_chip_manifest.tsv`
- Output TSV: `data/viladonga-pilot/pnoa_shape_baseline.tsv`
- Baseline: `centered_positive_shape_template`
- Rows checked: 9
- OK rows: 9
- Failed rows: 0
- Signal status: `pnoa_shape_signal_ambiguous`

## Positive Row

- Chip: `viladonga-pnoa-positive-1`
- Edge ratio: 0.955498
- Edge-ratio rank: 2 of 9
- Negative median edge ratio: 0.852193
- Texture ratio: 1.284275
- Luminance delta: 0.265399

## Signal Reading

PNOA is visually useful but not decisive as a shape detector. The positive chip ranks above the negative median, yet the result is not clean enough to treat PNOA-only edges as a reliable morphology signal. Relief products should carry the next baseline.

## Top Edge Ratios

| Rank | Chip | Class | Edge ratio | Texture ratio |
|---:|---|---:|---:|---:|
| 1 | `viladonga-pnoa-negative-2` | 0 | 0.973643 | 0.774736 |
| 2 | `viladonga-pnoa-positive-1` | 1 | 0.955498 | 1.284275 |
| 3 | `viladonga-pnoa-negative-6` | 0 | 0.928095 | 0.952819 |
| 4 | `viladonga-pnoa-negative-7` | 0 | 0.881069 | 0.711272 |
| 5 | `viladonga-pnoa-negative-9` | 0 | 0.864082 | 0.938046 |

## Interpretation

This is a smoke-test baseline, not a detector. The positive mask is used as the real contour for Viladonga and as a centered template for the negative chips. The score asks a narrow question: does a castro-sized boundary ring show more PNOA edge signal than nearby context, and does the positive chip rank above the negatives?

A strong result here would justify spending time on a relief-aware baseline and on the correct LAZ tiles. A weak or ambiguous result means PNOA alone should stay as visual support while LiDAR/DTM remains the main morphology signal.
