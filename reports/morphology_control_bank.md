# Morphology Control Bank

Generated: 2026-08-01T00:00:00Z

## Scope

This bank broadens the Viladonga pilot into a Galicia plus northern Portugal review corpus. It deliberately separates official positive castro/citania/cividade seeds from official non-castro heritage distractors. None of these points are final training polygons.

## Official Sources

- Xunta PBA layer 11: https://ideg.xunta.gal/servizos/rest/services/PBA/Afeccions_PatrimonioCultural/MapServer/11
- Xunta data catalogue: https://datos.gob.es/es/catalogo/a12002994-plan-basico-autonomico-de-galicia-afecciones-del-patrimonio-cultural
- DGPC/Portal do Arqueologo ArcGIS item: https://www.arcgis.com/home/item.html?id=051ecb3b6f1048cebdab360de305fae4
- DGPC/Portal do Arqueologo service: https://geo.patrimoniocultural.gov.pt/arcgis/rest/services/PatrimonioArqueologico/Sitios_Arqueologicos/MapServer
- DGPC/Portal do Arqueologo layer: https://geo.patrimoniocultural.gov.pt/arcgis/rest/services/PatrimonioArqueologico/Sitios_Arqueologicos/MapServer/0

## Counts

- Positive official castro-like seeds: 3929
- Official non-castro hard-negative distractors: 10845
- Stratified QGIS review seed: 2400 (1200 positive, 1200 negative)

### Positives by Country

- ES: 3630
- PT: 299

### Positives by Confidence

- medium_official_name_or_type: 2669
- high_official_typology: 1259
- low_toponymic_review: 1

### Positives by Morphology Proxy

- generic_castro_hint: 2701
- hilltop_hint: 415
- earthwork_or_wall_hint: 221
- coastal_promontory_hint: 197
- croa_top_ring_hint: 163
- castrel_toponym_hint: 135
- valley_or_river_edge_hint: 73
- large_castrexo_civitas_hint: 24

### Positive Places

- ES:A Coruña: 1311
- ES:Lugo: 1241
- ES:Pontevedra: 653
- ES:Ourense: 425
- PT:Bragança: 75
- PT:Vila Real: 74
- PT:Braga: 60
- PT:Viana do Castelo: 54
- PT:Porto: 36

### Negatives by Country

- ES: 10280
- PT: 565

### Negatives by Type

- megalithic_mound: 7521
- rock_art_surface: 2706
- roman_built_context: 220
- mining_or_quarry: 161
- necropolis_or_burial: 118
- historic_fortification: 81
- necropolis_or_burial;roman_built_context: 22
- megalithic_mound;rock_art_surface: 11
- rock_art_surface;roman_built_context: 3
- historic_fortification;roman_built_context: 2

### Negative Places

- ES:A Coruña: 3298
- ES:Pontevedra: 3062
- ES:Lugo: 3020
- ES:Ourense: 900
- PT:Braga: 168
- PT:Viana do Castelo: 149
- PT:Porto: 116
- PT:Bragança: 66
- PT:Vila Real: 66

## Files

- data/morphology-bank/positive_castro_sources.tsv
- data/morphology-bank/positive_castro_sources.geojson
- data/morphology-bank/negative_distractor_sources.tsv
- data/morphology-bank/negative_distractor_sources.geojson
- data/morphology-bank/morphology_control_review_seed.tsv
- data/morphology-bank/morphology_control_review_seed.geojson
- data/morphology-bank/morphology_strata_summary.tsv
- data/morphology-bank/source_register.tsv

## Review Rules

- Positive rows are catalogue seeds, not final site boundaries.
- Morphology proxies are name/type heuristics used only to diversify QGIS review.
- Negative rows are official non-castro heritage distractors; they still require visual review before training.
- Natural empty-terrain negatives should be generated later from raster tiles after buffering away all catalogue heritage seeds.
