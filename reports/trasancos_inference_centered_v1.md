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
| `1` | `1.00000000` | `-8.27` | `43.42` | `15.0` | `120.0` | `-2.381` |
| `2` | `1.00000000` | `-8.30` | `43.43` | `15.0` | `120.0` | `-2.161` |
| `8` | `1.00000000` | `-8.19` | `43.48` | `15.0` | `120.0` | `-0.606` |
| `9` | `1.00000000` | `-8.32` | `43.53` | `30.0` | `180.0` | `3.080` |
| `10` | `1.00000000` | `-8.32` | `43.55` | `30.0` | `220.0` | `0.947` |
| `13` | `1.00000000` | `-8.22` | `43.58` | `30.0` | `120.0` | `2.396` |
| `14` | `1.00000000` | `-8.22` | `43.59` | `15.0` | `180.0` | `0.022` |
| `15` | `1.00000000` | `-8.20` | `43.60` | `15.0` | `120.0` | `-2.989` |
| `16` | `1.00000000` | `-8.19` | `43.62` | `30.0` | `120.0` | `-0.491` |
| `20` | `0.99999989` | `-8.25` | `43.49` | `15.0` | `150.0` | `0.165` |
| `22` | `0.99999948` | `-8.30` | `43.46` | `15.0` | `150.0` | `-1.238` |
| `23` | `0.99999444` | `-8.08` | `43.65` | `15.0` | `150.0` | `21.076` |
| `24` | `0.99999097` | `-8.18` | `43.42` | `15.0` | `150.0` | `-0.588` |
| `25` | `0.99998493` | `-8.21` | `43.59` | `30.0` | `120.0` | `36.332` |
| `26` | `0.99998397` | `-8.17` | `43.49` | `15.0` | `150.0` | `1.331` |
| `27` | `0.99998164` | `-8.28` | `43.46` | `15.0` | `120.0` | `-2.876` |
| `28` | `0.99996055` | `-8.29` | `43.46` | `15.0` | `120.0` | `-2.097` |
| `29` | `0.99993024` | `-8.12` | `43.64` | `30.0` | `120.0` | `14.480` |
| `30` | `0.99986686` | `-8.25` | `43.48` | `15.0` | `150.0` | `14.024` |
| `31` | `0.99985723` | `-8.27` | `43.43` | `60.0` | `150.0` | `-2.510` |
| `32` | `0.99982684` | `-8.14` | `43.63` | `30.0` | `120.0` | `-45.597` |
| `33` | `0.99981015` | `-8.25` | `43.49` | `15.0` | `150.0` | `11.976` |
| `34` | `0.99976762` | `-8.30` | `43.53` | `30.0` | `150.0` | `-1.482` |
| `35` | `0.99957461` | `-8.20` | `43.61` | `60.0` | `80.0` | `17.512` |
| `36` | `0.99855193` | `-8.26` | `43.47` | `15.0` | `120.0` | `-1.681` |
| `37` | `0.99846342` | `-8.21` | `43.59` | `60.0` | `150.0` | `-50.236` |
| `38` | `0.99836209` | `-8.11` | `43.65` | `60.0` | `80.0` | `29.126` |
| `39` | `0.99836023` | `-8.08` | `43.60` | `30.0` | `120.0` | `6.285` |
| `42` | `0.99811973` | `-8.27` | `43.46` | `15.0` | `120.0` | `-2.038` |
| `43` | `0.99792237` | `-8.05` | `43.46` | `60.0` | `40.0` | `9.157` |
| `44` | `0.99729940` | `-8.13` | `43.43` | `60.0` | `120.0` | `-20.919` |
| `45` | `0.99699832` | `-8.08` | `43.64` | `240.0` | `180.0` | `43.861` |
| `47` | `0.99688578` | `-8.08` | `43.65` | `15.0` | `180.0` | `32.316` |
| `48` | `0.99655942` | `-8.25` | `43.48` | `30.0` | `100.0` | `4.178` |
| `49` | `0.99634746` | `-8.32` | `43.55` | `30.0` | `80.0` | `20.851` |
| `50` | `0.99603050` | `-8.17` | `43.51` | `15.0` | `120.0` | `11.385` |
| `51` | `0.99548470` | `-8.22` | `43.59` | `15.0` | `120.0` | `-0.367` |
| `52` | `0.99539553` | `-8.32` | `43.55` | `60.0` | `100.0` | `26.834` |
| `53` | `0.99461701` | `-8.21` | `43.45` | `60.0` | `40.0` | `15.992` |
| `54` | `0.99382102` | `-8.06` | `43.52` | `60.0` | `100.0` | `9.817` |

## Cautions

- Weak labels trained this model. A high score is a shape prior, not a site.
- The dominant false positive in every evaluation so far is the mámoa;
  expect burial mounds near the top and check `negative_type` history.
- Nothing here is a discovery claim. No precise coordinate of an
  uncatalogued cell goes into any public artefact, repo README, web map
  or wiki page before archaeological review.
- Sea and estuary cells are flagged, not deleted, so the exclusion stays
  auditable.

