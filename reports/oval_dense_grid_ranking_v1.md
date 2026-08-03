# Trasancos inference ranking v1

Generated at: `2026-08-02T00:00:00Z`
Grid step: `128 m` · tile side: `512 m` · bbox: `-8.2411,43.5346,-8.1932,43.5890`
Model: `data/weak-label-fusion-v1/weak_label_rgb_relief_msrm_full_model.json`

## What this is

Every earlier metric ranked catalogued points. This ranks a blind grid
over the comarca, so the model has to commit on ground nobody pre-selected.
A high rank here is a place worth opening in QGIS, nothing more.

## Coverage

- grid cells: `1488`
- scored ok: `1488`
- sea/flat excluded: `130`
- missing RGB: `0`
- missing DEM: `0`
- errors: `0`

## Sanity check: does it find what we already know?

- catalogued castros inside the grid: `22`
- of those, ranked in the top decile of land cells: `11`

If the model cannot re-find catalogued castros on a blind grid, its
uncatalogued candidates carry no weight. Read this number first.

## Candidate classes

| class | cells |
|---|---:|
| `uncatalogued_candidate` | `1321` |
| `sea_or_flat_excluded` | `130` |
| `known_castro_recovered` | `22` |
| `known_megalithic_mound` | `15` |

## Top `40` uncatalogued cells

Coordinates are rounded here on purpose. Precise positions live in the
TSV/GeoJSON, which stay internal.

| rank | probability | approx lon | approx lat | dominant scale (m) | best ring (m) | prominence (m) |
|---:|---:|---:|---:|---:|---:|---:|
| `1` | `1.00000000` | `-8.23` | `43.58` | `15.0` | `60.0` | `-0.001` |
| `2` | `0.99137176` | `-8.22` | `43.59` | `60.0` | `40.0` | `43.207` |
| `3` | `0.98600630` | `-8.23` | `43.57` | `30.0` | `120.0` | `25.772` |
| `4` | `0.95984791` | `-8.24` | `43.57` | `60.0` | `120.0` | `10.116` |
| `5` | `0.94653244` | `-8.24` | `43.54` | `240.0` | `80.0` | `29.170` |
| `6` | `0.94077495` | `-8.23` | `43.57` | `15.0` | `150.0` | `27.378` |
| `7` | `0.91660749` | `-8.23` | `43.56` | `120.0` | `120.0` | `6.235` |
| `8` | `0.91302750` | `-8.22` | `43.56` | `60.0` | `120.0` | `5.577` |
| `10` | `0.89722713` | `-8.23` | `43.57` | `120.0` | `100.0` | `28.562` |
| `12` | `0.88696447` | `-8.21` | `43.57` | `240.0` | `40.0` | `7.033` |
| `13` | `0.87029593` | `-8.24` | `43.55` | `120.0` | `120.0` | `-5.074` |
| `14` | `0.86677795` | `-8.23` | `43.57` | `240.0` | `60.0` | `52.863` |
| `15` | `0.86593614` | `-8.19` | `43.59` | `60.0` | `100.0` | `-7.482` |
| `16` | `0.85701442` | `-8.20` | `43.56` | `30.0` | `100.0` | `2.315` |
| `17` | `0.85300535` | `-8.23` | `43.57` | `15.0` | `150.0` | `31.721` |
| `18` | `0.84952101` | `-8.20` | `43.58` | `30.0` | `40.0` | `6.843` |
| `19` | `0.84684737` | `-8.22` | `43.54` | `30.0` | `80.0` | `5.551` |
| `20` | `0.84624964` | `-8.21` | `43.59` | `120.0` | `60.0` | `6.125` |
| `21` | `0.84517955` | `-8.24` | `43.57` | `30.0` | `60.0` | `36.600` |
| `22` | `0.84245796` | `-8.20` | `43.57` | `120.0` | `120.0` | `3.182` |
| `23` | `0.83778490` | `-8.24` | `43.53` | `240.0` | `40.0` | `46.776` |
| `25` | `0.83287761` | `-8.22` | `43.57` | `240.0` | `120.0` | `35.335` |
| `26` | `0.83025790` | `-8.23` | `43.55` | `240.0` | `60.0` | `32.478` |
| `27` | `0.81884022` | `-8.20` | `43.55` | `60.0` | `80.0` | `1.360` |
| `28` | `0.80996961` | `-8.22` | `43.59` | `30.0` | `180.0` | `31.177` |
| `29` | `0.80255712` | `-8.21` | `43.57` | `120.0` | `150.0` | `6.166` |
| `30` | `0.79286535` | `-8.20` | `43.55` | `60.0` | `180.0` | `8.032` |
| `31` | `0.77840006` | `-8.20` | `43.59` | `60.0` | `40.0` | `10.356` |
| `32` | `0.77831431` | `-8.22` | `43.59` | `240.0` | `60.0` | `46.782` |
| `33` | `0.77593085` | `-8.22` | `43.56` | `120.0` | `40.0` | `3.701` |
| `34` | `0.77148763` | `-8.24` | `43.55` | `120.0` | `120.0` | `27.476` |
| `35` | `0.75880290` | `-8.23` | `43.54` | `15.0` | `80.0` | `19.428` |
| `36` | `0.75355208` | `-8.20` | `43.58` | `30.0` | `120.0` | `0.843` |
| `37` | `0.75056061` | `-8.21` | `43.57` | `240.0` | `60.0` | `15.134` |
| `38` | `0.74573962` | `-8.20` | `43.58` | `60.0` | `80.0` | `-3.247` |
| `39` | `0.73847788` | `-8.23` | `43.55` | `240.0` | `80.0` | `32.924` |
| `40` | `0.72313849` | `-8.22` | `43.57` | `240.0` | `80.0` | `20.955` |
| `41` | `0.71876877` | `-8.22` | `43.57` | `60.0` | `150.0` | `16.960` |
| `42` | `0.71389466` | `-8.21` | `43.58` | `240.0` | `150.0` | `18.179` |
| `43` | `0.71208200` | `-8.24` | `43.55` | `240.0` | `100.0` | `31.432` |

## Cautions

- Weak labels trained this model. A high score is a shape prior, not a site.
- The dominant false positive in every evaluation so far is the mámoa;
  expect burial mounds near the top and check `negative_type` history.
- Nothing here is a discovery claim. No precise coordinate of an
  uncatalogued cell goes into any public artefact, repo README, web map
  or wiki page before archaeological review.
- Sea and estuary cells are flagged, not deleted, so the exclusion stays
  auditable.

