# Multitemporal Sentinel-2: does it separate castros from mámoas?

Sites with usable series: `40` castros, `40` mámoas (from `80` attempted).
Window: `2022-01-01` to `2025-12-31`, cloud `< 25%`, up to `8` dates per site, `10 m` bands B04/B08.

## What this measures

Satellites do not see underground. They see crop and soil marks: plants
over a buried wall run short of water and senesce early, plants over a
filled ditch stay green longer. The mark only appears under the right
moisture and phenology, so the informative variable is **time**, not band
count. This is why Sentinel-2 at `10 m` beats hyperspectral at `30 m`
for features of this size.

## Separation (sigmas, higher is better)

| feature | separation |
|---|---:|
| `ndvi_median` | `1.18` |
| `ndvi_std_over_time` | `0.64` |
| `ndvi_range` | `0.71` |
| `core_contrast_median` | `0.06` |
| `core_contrast_abs_max` | `0.47` |
| `spec_brightness` | `1.12` |
| `spec_shape_std` | `0.56` |
| `spec_swir_vis_ratio` | `0.05` |
| `spec_rededge_slope` | `1.10` |

## Reference points from the same project

| source | best separation |
|---|---:|
| OSM polygon radius (geometry) | `1.38` |
| MDT5 relief descriptors | `1.15` |
| LiDAR 1 m relief descriptors | `0.90` |
| **Sentinel-2 multitemporal NDVI** | **`1.18`** |

## Verdict

- **Adds real signal.** Sentinel-2 matches or beats the relief descriptors and is worth folding into the feature set.

- Caveat: at `10 m`, a `20 m` mámoa is about `2x2` pixels. Weak separation
  may reflect that mámoas are simply too small for this sensor, not that
  crop marks are uninformative in general.

