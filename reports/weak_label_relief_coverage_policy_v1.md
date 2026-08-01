# Weak-label relief coverage policy v1

Generated: 2026-08-01T00:00:00Z

## Decision

The current RGB+relief baseline is a Spain-relief experiment. Portuguese rows remain valid for RGB-only diagnostics, but they must not be treated as relief failures or mixed into fused relief metrics until a separate Portugal DEM/DTM provider is implemented and audited.

Operational policy:

- `ES` rows with valid MDT5 chips can enter `relief_fusion_v1`.
- `PT` rows stay `rgb_only_until_portugal_dem_provider`.
- Global metrics must be reported as `RGB all`, `relief-valid Spain`, and `Portugal RGB-only/pending DEM`, not as one uniform fused benchmark.
- Any Portugal relief v2 must write provider, CRS, vertical reference, resolution and source availability per tile.

## Files

- Coverage summary: `data/weak-label-relief-v1/weak_label_relief_coverage_policy.tsv`
- Planned split country summary: `data/weak-label-relief-v1/weak_label_relief_planned_country_summary.tsv`
- Unsupported Portugal rows: `data/weak-label-relief-v1/weak_label_relief_unsupported_country_rows.tsv`

## Existing Export Coverage

| dataset | total | relief_valid | unsupported_country | failed_or_invalid | missing | relief_usable_rate |
| --- | --- | --- | --- | --- | --- | --- |
| holdouts | 204 | 204 | 0 | 0 | 0 | 1.000000 |
| train_mini | 1000 | 553 | 447 | 0 | 0 | 0.553000 |
| val | 2037 | 1851 | 186 | 0 | 0 | 0.908689 |

## Detail By Split, Country And Role

| dataset | final_split | country | label_role | total_rows | relief_valid_rows | relief_unsupported_country_rows | policy_bucket |
| --- | --- | --- | --- | --- | --- | --- | --- |
| holdouts | test_o_val | ES | hard_negative | 1 | 1 | 0 | relief_fusion_v1_allowed |
| holdouts | test_o_val | ES | positive | 4 | 4 | 0 | relief_fusion_v1_allowed |
| holdouts | test_trasancos | ES | hard_negative | 135 | 135 | 0 | relief_fusion_v1_allowed |
| holdouts | test_trasancos | ES | positive | 64 | 64 | 0 | relief_fusion_v1_allowed |
| val | val | ES | hard_negative | 1492 | 1492 | 0 | relief_fusion_v1_allowed |
| val | val | ES | positive | 359 | 359 | 0 | relief_fusion_v1_allowed |
| val | val | PT | hard_negative | 120 | 0 | 120 | rgb_only_until_portugal_dem_provider |
| val | val | PT | positive | 66 | 0 | 66 | rgb_only_until_portugal_dem_provider |
| train_mini | train | ES | hard_negative | 277 | 277 | 0 | relief_fusion_v1_allowed |
| train_mini | train | ES | positive | 276 | 276 | 0 | relief_fusion_v1_allowed |
| train_mini | train | PT | hard_negative | 277 | 0 | 277 | rgb_only_until_portugal_dem_provider |
| train_mini | train | PT | positive | 170 | 0 | 170 | rgb_only_until_portugal_dem_provider |

## Planned Weak-label Footprint

- Planned ES rows: `13079`.
- Planned PT rows: `837`.

| final_split | country | label_role | planned_rows | policy_bucket |
| --- | --- | --- | --- | --- |
| test | ES | hard_negative | 1855 | planned_spanish_mdt5_provider |
| test | ES | positive | 528 | planned_spanish_mdt5_provider |
| test | PT | hard_negative | 111 | planned_relief_provider_needed |
| test | PT | positive | 36 | planned_relief_provider_needed |
| test_o_val | ES | hard_negative | 1 | planned_spanish_mdt5_provider |
| test_o_val | ES | positive | 4 | planned_spanish_mdt5_provider |
| test_trasancos | ES | hard_negative | 135 | planned_spanish_mdt5_provider |
| test_trasancos | ES | positive | 64 | planned_spanish_mdt5_provider |
| train | ES | hard_negative | 6797 | planned_spanish_mdt5_provider |
| train | ES | positive | 1844 | planned_spanish_mdt5_provider |
| train | PT | hard_negative | 334 | planned_relief_provider_needed |
| train | PT | positive | 170 | planned_relief_provider_needed |
| val | ES | hard_negative | 1492 | planned_spanish_mdt5_provider |
| val | ES | positive | 359 | planned_spanish_mdt5_provider |
| val | PT | hard_negative | 120 | planned_relief_provider_needed |
| val | PT | positive | 66 | planned_relief_provider_needed |

## Official Portugal Relief Sources Checked

### DGT Modelos Digitais do Relevo

- URL: https://www.dgterritorio.gov.pt/atividades/cartografia/cartografia-topografica/modelos-digitais
- Evidence: Portugal continental has LiDAR access through the DGT data centre or the QGIS CDD Downloader plugin, with LAZ and derived MDT/MDS GeoTIFF products at 0.5 m, 2 m and 10 m.
- Implication: Portugal needs its own DGT/CDD ingestion path; the current Spanish WCS target should not be stretched across the border.

### DGT LiDAR Portugal Continental

- URL: https://www.dgterritorio.gov.pt/levantamento-lidar-de-portugal-continental-0
- Evidence: DGT states that the 2024-2025 LiDAR data can be downloaded from the DGT data centre, that each access is limited to about 200 km2, and that an API is planned; about 90% of mainland coverage is available while the northwest remains in production.
- Implication: Northern Portugal may still have holes; the pipeline must record download availability per tile before using Portuguese relief in metrics.

### dados.gov.pt LiDAR Portugal Continental

- URL: https://dados.gov.pt/pt/datasets/dados-lidar-de-portugal-continental/
- Evidence: The open-data catalogue describes 2024 airborne LiDAR, 10 points/m2, LAS point clouds and MDT/MDS products at 50 cm and 2 m resolution under CC BY 4.0.
- Implication: The correct Portugal relief v2 source is technically strong, but it is a separate provider and CRS/vertical-datum problem.

## Why This Remains Blocked For Fusion

The Spanish export script requests `Elevacion25830_5` from the Spanish MDT WCS in `EPSG:25830`. That is correct for Spain/Galicia, but not for Portugal. DGT Portugal exposes strong LiDAR/MDT data, yet through a different distribution path and Portuguese reference system. Mixing those two without an explicit provider adapter would make the model look more complete than it is.

The immediate unblock is therefore not to fake Portuguese relief, but to keep v1 honest and add a Portugal DEM provider as a separate v2 task.

## Next Engineering Step

Build `export_weak_label_relief_dgt_pt.py` only after a small CDD inventory test confirms tile addressing, download URLs, CRS, licensing metadata and coverage in the north of Portugal. Until then, use RGB for Portugal and relief/fusion for Spain.

## Unsupported Row Sample

| dataset | final_split | label_role | name | municipality | dem_status |
| --- | --- | --- | --- | --- | --- |
| val | val | hard_negative | Abrigo 11 da Ribeira da Cabreira/ Ribeira da Cabreira 11 |  | unsupported_country |
| val | val | hard_negative | Abrigo 3 da Ribeira da Cabreira/ Ribeira da Cabreira 3 |  | unsupported_country |
| val | val | hard_negative | Alto de Pandim / Gouvães da Serra |  | unsupported_country |
| val | val | hard_negative | Alto do Cemitério Velho / Parada de monteiros |  | unsupported_country |
| val | val | hard_negative | Anta de Zedes (Casa da Moura I) |  | unsupported_country |
| val | val | hard_negative | Aqueduto da Serra do Pilar/Aqueduto do Sardão |  | unsupported_country |
| val | val | hard_negative | Ara de Louredo |  | unsupported_country |
| val | val | hard_negative | Arca 1 |  | unsupported_country |
| val | val | hard_negative | Arquinho 2 |  | unsupported_country |
| val | val | hard_negative | Batocas/ Lamas da Cidade |  | unsupported_country |
| val | val | hard_negative | Cabanelas |  | unsupported_country |
| val | val | hard_negative | Calçada Romana de Brito |  | unsupported_country |
| val | val | hard_negative | Calçada da Belavista |  | unsupported_country |
| val | val | hard_negative | Calçada de Novias |  | unsupported_country |
| val | val | hard_negative | Canelas / Paranho |  | unsupported_country |
| val | val | hard_negative | Capela de Crasto |  | unsupported_country |
| val | val | hard_negative | Carvalhal 1 |  | unsupported_country |
| val | val | hard_negative | Carvalhal 2 |  | unsupported_country |
| val | val | hard_negative | Carvalhas Alvas 2 |  | unsupported_country |
| val | val | hard_negative | Castelo de Crestuma |  | unsupported_country |
| ... | 613 more rows not shown |  |  |  |  |
