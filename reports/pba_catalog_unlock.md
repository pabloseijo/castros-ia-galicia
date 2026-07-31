# PBA catalogue unlock report

Generated: 2026-07-31T12:45:40Z

## Fact-checked sources

- Datos.gob dataset: https://datos.gob.es/es/catalogo/a12002994-plan-basico-autonomico-de-galicia-afecciones-del-patrimonio-cultural
- ArcGIS REST service: https://ideg.xunta.gal/servizos/rest/services/PBA/Afeccions_PatrimonioCultural/MapServer
- Queried feature layer: 11 / Catálogo. Elementos (xuño 2026)
- CRS returned by the service is ETRS89 / UTM zone 29N in X/Y, with WGS84 lon/lat requested via `outSR=4326` for the candidate table.

## Summary

- PBA heritage rows queried for Trasancos municipalities: 252
- Geocoding blockers analysed: 26
- coordinate_for_damaged_review: 1
- coordinate_for_review: 2
- coordinate_for_review_not_training: 3
- coordinate_for_review_reconcile_duplicate: 2
- coordinate_for_toponymic_review: 1
- duplicate_or_alias: 7
- duplicate_possible_needs_human: 1
- still_blocked: 9

## Operational reading

- Rows marked `coordinate_for_*` can be placed in QGIS from PBA, but still need human review before they become labels.
- Rows marked `duplicate_or_alias` should be merged or discarded against the stronger existing official row instead of becoming extra positives.
- Rows marked `still_blocked` did not get enough official support from this PBA pass.
- `coordinate_for_review_not_training` is deliberately strict: a coordinate exists, but the PBA typology/toponym does not support using it as a castro training positive.

## Decisions

| Site | Decision | PBA candidate | Code | Typology | WGS84 | Reason |
|---|---|---|---|---|---|---|
| Castro de Almieiras | still_blocked |  |  |  |  | No PBA catalogue hit for Almieiras/Limodre in the queried fields. |
| Castro de Fontenova | duplicate_or_alias | Castro de Magalofes / Magalofes (San Xurxo) / Fontenova, A | GA15035007 |  | 43.45066168, -8.14730872 | PBA has Castro de Magalofes at A Fontenova; dataset already has GA15035007 as a separate row. |
| Castro de Cordoeiro | coordinate_for_review_reconcile_duplicate | Castro das Pías/Castro de Cardoeiro / Perlío (Santo Estevo) / Cruceiro, O | GA15035011 | Castro | 43.47427555, -8.17157251 | Exact code match, but PBA names it Castro das Pias/Castro de Cardoeiro and flags location/duplicate in OBSERVACIO. |
| Castro de Loureiros | duplicate_or_alias | Castro de Barallobre / Barallobre (Santiago) / Loureiros, Os | GA15035010 |  | 43.46407351, -8.17875950 | PBA has Castro de Barallobre in Os Loureiros; treat the Pena row as a damaged/alias row to reconcile. |
| Castro de Ovra | duplicate_or_alias | Castro de Orra / Sillobre (Santa Mariña) / Orra | GA15035009 |  | 43.47117366, -8.15262685 | PBA has Castro de Orra in Sillobre; likely Ovra/Orra spelling reconciliation, not a new site. |
| Castro do Sartego | still_blocked |  |  |  |  | No PBA hit for RE15035002 or Castro do Sartego; only an unrelated Sartego da Fonte dos Mouros achado appears. |
| Castro de San Esteban de Perlío | duplicate_possible_needs_human | Castro das Pías/Castro de Cardoeiro / Perlío (Santo Estevo) / Cruceiro, O | GA15035011 | Castro | 43.47427555, -8.17157251 | Likely points toward the As Pias/Cardoeiro/Cordoeiro cluster, but name-only evidence is too weak to geocode automatically. |
| Castro de Canido | coordinate_for_damaged_review | Castro de Canido / Ferrol / Ferrol | RE15036007 |  | 43.48378571, -8.24272308 | Exact PBA reference-name match; keep review-only because the source row is marked damaged/disappeared. |
| Castro de Ferreiros | still_blocked |  |  |  |  | PBA match for Ferreiros is a mamoa in Brion, not Castro de Ferreiros in Mandia. |
| Castro de O Xeixo | duplicate_or_alias | Castro de Leixa/A Croa de Leixa / Leixa (San Pedro) / San Pedro de Leixa | GA15036006 |  | 43.52270698, -8.20836441 | PBA has Castro de Leixa/A Croa de Leixa in San Pedro de Leixa; likely the same target as O Xeixo. |
| Castro de Papoy | duplicate_or_alias | Castro de Marmancón/Castro de Papoi / Marmancón (San Pedro) / Rilo | GA15036003 |  | 43.53963295, -8.24912869 | PBA has Castro de Marmancon/Castro de Papoi; Papoy should reconcile to that existing official row. |
| O Castro | duplicate_or_alias | Castro de Petouzal/Castro da Croa / Narón / Castro, O | GA15054006 | Castro | 43.50162952, -8.17901516 | PBA has Castro de Petouzal/Castro da Croa in O Castro/Couto; dataset already has the official Petouzal row. |
| Castros | coordinate_for_review_not_training | Castros / Santa María de Neda (Santa María) / Castros, Os | TO15055002 |  | 43.50786202, -8.14974046 | Exact topographic/toponymic PBA reference; not enough to promote as a training positive. |
| Monte de Rabadeña | coordinate_for_review_not_training | Cazoletas do Monte da Rabadeña / Santa María de Neda (Santa María) / Rabadeña, A | GA15055005 |  | 43.48941090, -8.14994502 | Exact code from the prior note, but PBA names it Cazoletas do Monte da Rabadena, not a castro. |
| Castro de Santa María de Neda | still_blocked |  |  |  |  | Same parish as Castro de Ancos, but no PBA name/code supports automatic equivalence. |
| A Croa / Naraío | coordinate_for_toponymic_review | A Croa / Naraío (Santa María) / O Batán |  |  | 43.48946911, -8.08100028 | PBA has A Croa in Naraio/O Batan, but no ID_IPAGA; keep toponymic review-only. |
| Castro das Croas | coordinate_for_review_reconcile_duplicate | Castro Das Croas / San Sadurniño (Santa María) / A Rubiña | GA15076006 |  | 43.54359118, -8.06556224 | Strong PBA name match; reconcile with existing Castro de San Sadurnino/Galipedia row before training. |
| Coto da Croa ou A Croa do Castro | coordinate_for_review | Coto da Croa / Bardaos (Santa María) / O Castro | GA15076005 |  | 43.57797902, -8.03282626 | PBA has Coto da Croa in Bardaos/O Castro. |
| Coto da Croa ou A Croa do Castro | coordinate_for_review | A Croa do Castro / Santa Mariña do Monte (Santa Mariña) / Escoitadoira | GA15076004 |  | 43.58051086, -8.07339525 | PBA has A Croa do Castro in Santa Marina do Monte/Escoitadoira. |
| Castro de Fraga | still_blocked |  |  |  |  | No PBA Castro de Fraga match in San Sadurnino/Bardaos. |
| O Picho | still_blocked |  |  |  |  | PBA Picho hits are fountains, not castro evidence. |
| Castro de San Cristóbal | still_blocked |  |  |  |  | No PBA San Cristobal/San Sadurnino castro match in the queried layer. |
| Tralocastro | still_blocked |  |  |  |  | No San Sadurnino Tralocastro hit; Ferrol Tralocastro is a different official site. |
| Castro de As Filgueiras | still_blocked |  |  |  |  | PBA Filgueiras hits are in San Sadurnino and are not Valdovino/Meiras castros. |
| Puerto de Meirás | coordinate_for_review_not_training | Porto de Meirás / Meirás (San Vicente) / Carballoso, O | GA15087017 | Medieval | 43.61149393, -8.19140506 | Exact code match, but PBA typology is Medieval, so do not use as castro training positive without review. |
| Castro de Praia Frouxeira | duplicate_or_alias | Castro de Punta Frouxeira / Valdoviño (Santaia) / Saíña, A | GA15087009 | Castro | 43.61848040, -8.14887288 | PBA has Castro de Punta Frouxeira; reconcile with existing official GA15087009 row. |

## Next unblock actions

1. Merge/discard duplicate alias rows before expanding training positives.
2. Add PBA coordinates only to review queues, not directly to `labels_reviewed`.
3. For `still_blocked` rows, use the PBA visor/PXOM PDFs manually or remove them from the MVP geospatial scope.
4. After QGIS review, draw accepted positives in `labels_reviewed` and accepted negative areas in `negative_areas_reviewed`.

## Generated queues

- `data/review-queues/pba_geocode_candidates.tsv`: official PBA coordinates that can be checked in QGIS.
- `data/review-queues/pba_duplicate_aliases.tsv`: rows that should probably be merged/discarded against stronger existing records.
- `data/review-queues/pba_still_blocked.tsv`: rows still lacking enough official support after this PBA pass.
