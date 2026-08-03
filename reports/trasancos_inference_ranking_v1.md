# Trasancos inference ranking v1

Generated at: `2026-08-02T00:00:00Z`
Grid step: `512 m` · tile side: `512 m` · bbox: `-8.33,43.42,-7.99,43.65`
Model: `data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_model.json`

## What this is

Every earlier metric ranked catalogued points. This ranks a blind grid
over the comarca, so the model has to commit on ground nobody pre-selected.
A high rank here is a place worth opening in QGIS, nothing more.

## Coverage

- grid cells: `2754`
- scored ok: `2753`
- sea/flat excluded: `580`
- missing RGB: `1`
- missing DEM: `0`
- errors: `0`

## Sanity check: does it find what we already know?

- catalogued castros inside the grid: `82`
- of those, ranked in the top decile of land cells: `15`

If the model cannot re-find catalogued castros on a blind grid, its
uncatalogued candidates carry no weight. Read this number first.

## Candidate classes

| class | cells |
|---|---:|
| `uncatalogued_candidate` | `2017` |
| `sea_or_flat_excluded` | `580` |
| `known_castro_recovered` | `82` |
| `known_megalithic_mound` | `72` |
| `known_rock_art_surface` | `2` |

## Top `40` uncatalogued cells

Coordinates are rounded here on purpose. Precise positions live in the
TSV/GeoJSON, which stay internal.

| rank | probability | approx lon | approx lat | dominant scale (m) | best ring (m) | prominence (m) |
|---:|---:|---:|---:|---:|---:|---:|
| `1` | `1.00000000` | `-8.22` | `43.59` | `15.0` | `220.0` | `0.000` |
| `2` | `1.00000000` | `-8.12` | `43.65` | `15.0` | `100.0` | `0.096` |
| `3` | `0.99921472` | `-8.24` | `43.42` | `15.0` | `120.0` | `13.214` |
| `4` | `0.99240971` | `-8.25` | `43.48` | `15.0` | `100.0` | `3.598` |
| `5` | `0.98575830` | `-8.15` | `43.42` | `15.0` | `40.0` | `21.963` |
| `6` | `0.97903475` | `-8.07` | `43.65` | `60.0` | `120.0` | `16.785` |
| `8` | `0.96892690` | `-8.08` | `43.62` | `30.0` | `100.0` | `-15.612` |
| `10` | `0.96477142` | `-8.20` | `43.59` | `15.0` | `150.0` | `35.924` |
| `11` | `0.95950424` | `-8.21` | `43.43` | `240.0` | `40.0` | `9.528` |
| `12` | `0.95766255` | `-8.26` | `43.46` | `60.0` | `120.0` | `9.373` |
| `13` | `0.95282926` | `-8.01` | `43.52` | `60.0` | `40.0` | `8.505` |
| `15` | `0.94555369` | `-8.02` | `43.44` | `240.0` | `40.0` | `-5.647` |
| `16` | `0.93227831` | `-8.27` | `43.47` | `30.0` | `150.0` | `2.182` |
| `17` | `0.93204244` | `-8.17` | `43.42` | `60.0` | `60.0` | `16.518` |
| `19` | `0.92213670` | `-8.03` | `43.45` | `120.0` | `150.0` | `2.051` |
| `20` | `0.92157145` | `-8.31` | `43.50` | `60.0` | `40.0` | `13.530` |
| `22` | `0.92019231` | `-8.07` | `43.45` | `240.0` | `120.0` | `23.559` |
| `23` | `0.91728448` | `-8.09` | `43.61` | `60.0` | `120.0` | `4.259` |
| `24` | `0.91711874` | `-8.26` | `43.48` | `30.0` | `120.0` | `17.270` |
| `25` | `0.91639824` | `-8.27` | `43.46` | `240.0` | `220.0` | `33.789` |
| `26` | `0.91372259` | `-8.13` | `43.59` | `240.0` | `40.0` | `19.190` |
| `27` | `0.91108395` | `-8.15` | `43.42` | `30.0` | `180.0` | `22.673` |
| `28` | `0.90527659` | `-8.13` | `43.47` | `30.0` | `150.0` | `10.800` |
| `29` | `0.89785022` | `-8.23` | `43.57` | `60.0` | `60.0` | `9.056` |
| `30` | `0.88905268` | `-8.20` | `43.45` | `120.0` | `100.0` | `-3.567` |
| `31` | `0.88782844` | `-8.09` | `43.62` | `60.0` | `80.0` | `3.428` |
| `32` | `0.87820508` | `-7.99` | `43.57` | `240.0` | `60.0` | `8.316` |
| `33` | `0.87609704` | `-8.27` | `43.49` | `240.0` | `120.0` | `15.511` |
| `34` | `0.87538979` | `-8.02` | `43.51` | `240.0` | `120.0` | `31.060` |
| `35` | `0.87287707` | `-8.11` | `43.43` | `240.0` | `120.0` | `-32.676` |
| `36` | `0.86895125` | `-8.06` | `43.49` | `15.0` | `180.0` | `17.508` |
| `37` | `0.86767512` | `-8.04` | `43.45` | `240.0` | `120.0` | `7.903` |
| `38` | `0.86283494` | `-8.06` | `43.46` | `120.0` | `220.0` | `17.189` |
| `39` | `0.86177322` | `-8.03` | `43.59` | `15.0` | `40.0` | `5.923` |
| `40` | `0.85906128` | `-8.08` | `43.50` | `60.0` | `40.0` | `7.479` |
| `41` | `0.85678077` | `-8.03` | `43.49` | `240.0` | `40.0` | `26.898` |
| `42` | `0.85531786` | `-8.03` | `43.63` | `240.0` | `80.0` | `18.783` |
| `43` | `0.85431797` | `-8.10` | `43.57` | `30.0` | `150.0` | `4.508` |
| `44` | `0.85346127` | `-8.32` | `43.48` | `30.0` | `100.0` | `19.512` |
| `45` | `0.85302116` | `-8.08` | `43.50` | `30.0` | `180.0` | `18.809` |

## Cautions

- Weak labels trained this model. A high score is a shape prior, not a site.
- The dominant false positive in every evaluation so far is the mámoa;
  expect burial mounds near the top and check `negative_type` history.
- Nothing here is a discovery claim. No precise coordinate of an
  uncatalogued cell goes into any public artefact, repo README, web map
  or wiki page before archaeological review.
- Sea and estuary cells are flagged, not deleted, so the exclusion stays
  auditable.

