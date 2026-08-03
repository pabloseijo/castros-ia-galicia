# Weak-label MSRM multi-scale relief features v1

Generated at: `2026-08-02T00:00:00Z`
Scales (m): `15, 30, 60, 120, 240`
Ring radii swept (m): `40, 60, 80, 100, 120, 150, 180, 220`

## Coverage

- rows processed: `13916`
- rows ok: `13079`
- rows failed: `837`

## Dominant scale distribution (all rows)

| dominant_scale_m | rows |
|---|---:|
| `15.00000000` | `2862` |
| `30.00000000` | `1183` |
| `60.00000000` | `1338` |
| `120.00000000` | `1266` |
| `240.00000000` | `6430` |

## Dominant scale distribution (positives only)

| dominant_scale_m | positives |
|---|---:|
| `15.00000000` | `358` |
| `30.00000000` | `325` |
| `60.00000000` | `376` |
| `120.00000000` | `291` |
| `240.00000000` | `1449` |

## Best ring radius distribution

| best_ring_radius_m | rows |
|---|---:|
| `40.00000000` | `4376` |
| `60.00000000` | `1819` |
| `80.00000000` | `1527` |
| `100.00000000` | `1230` |
| `120.00000000` | `1151` |
| `150.00000000` | `1089` |
| `180.00000000` | `1258` |
| `220.00000000` | `629` |

## Standalone MSRM ranking metrics

| subset | rows | positives | ROC-AUC | AP | P@50 | R@50 | median positive rank |
|---|---:|---:|---:|---:|---:|---:|---:|
| `all` | `13079` | `2799` | `0.850794` | `0.661306` | `1.000000` | `0.017864` | `2057.0` |
| `train` | `8641` | `1844` | `0.850654` | `0.659415` | `1.000000` | `0.027115` | `1364.5` |
| `val` | `1851` | `359` | `0.858301` | `0.654879` | `0.900000` | `0.125348` | `266.0` |
| `test` | `2383` | `528` | `0.847127` | `0.663795` | `0.900000` | `0.085227` | `381.0` |
| `holdouts` | `204` | `68` | `0.848508` | `0.765596` | `0.760000` | `0.558824` | `42.5` |
| `test_trasancos` | `199` | `64` | `0.839352` | `0.739730` | `0.720000` | `0.562500` | `42.5` |
| `test_o_val` | `5` | `4` | `1.000000` | `1.000000` | `0.800000` | `1.000000` | `2.5` |

## Reading

These features are not a replacement ranker. They exist so the fusion
model can stop assuming a single castro size: `dominant_scale_m` and
`best_ring_radius_m` report the geometry each row actually answers to,
and the per-scale ratios expose small and large enclosures separately.
