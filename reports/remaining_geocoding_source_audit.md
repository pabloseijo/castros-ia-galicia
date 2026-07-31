# Remaining Geocoding Source Audit

Generated: 2026-07-31

Scope: second-pass source audit for the 9 rows still blocked after the PBA/Xunta catalogue query.

## Rule

This audit does not promote any row to a training label. It only classifies what kind of manual work remains.

The safest rule is still the same: no coordinate is assigned from a parish, a place name, a nearby castro, or a similar name alone.

## Sources Checked

- PBA/Xunta ArcGIS REST service, `PBA/Afeccions_PatrimonioCultural/MapServer`, especially `Catálogo. Elementos (xuño 2026)`.
- Cultura.gal catalogue guidance, which says catalogued immovable goods individually included in planning/urbanistic instruments form part of the Galician Cultural Heritage Catalogue while the full regulatory catalogue access is pending.
- Plan Sectorial da rede viaria de Ferrol, Fene, Neda, Narón, Ares, Mugardos e Cabanas (2014).
- PXOM Ferrol / SIOTUGA, catálogo de bienes protegidos.
- NNSS Neda / SIOTUGA.
- NNSS San Sadurniño / SIOTUGA, catálogo complementario.
- Concello de Valdoviño, Modificación Puntual nº 13, información patrimonial (2021).
- André Pena Graña, `Narón un concello con historia de seu I`, reedición Calaméo 2010, list `Catalogación de Castros de Galicia`.

## Result

- Strong new coordinate: 0.
- Possible official duplicate/equivalence for manual review: 2.
- Official reference but still no coordinate: 1.
- Classical/historical row still blocked: 6.

## Possible Equivalences

### `tra-ferrol-ferreiros` — Castro de Ferreiros

The classical list places Ferreiros in Santa Uxía de Mandiá. Ferrol PXOM and the PBA catalogue contain `GA15036005`, `Os Castros de Mandiá` / `Castro de Mandiá`, already represented in the MVP as `tra-ferrol-ga15036005`.

Decision: possible duplicate/equivalence only. Do not merge automatically, because the names and PBA parish/place metadata do not align cleanly.

### `tra-san-sadurnino-fraga` — Castro de Fraga

The classical list places Fraga in Bardaos. San Sadurniño NNSS and PBA support `Coto da Croa` / `A Croa do Castro` in Bardaos, which is already part of the review flow as a separate candidate.

Decision: possible Bardaos duplicate/toponym only. Do not assign the Bardaos coordinate automatically.

## Still Blocked

| Site | Status | Reason |
|---|---|---|
| Castro de Almieiras | classical damaged/no coordinate | The classical list marks it as disappeared; PBA has no Almieiras/Limodre hit. |
| Castro do Sartego | official reference/no coordinate | Plan Sectorial lists `RE15035002 Castro do Sartego`, but the PBA query did not return a matching castro point. |
| Castro de Santa María de Neda | classical damaged/no coordinate | Do not equate it automatically with Ancos or the separate Castros/toponymic row. |
| O Picho | weak toponym/no official castro | PBA/PDF hits point to fountains or weak nominal evidence, not a castro. |
| Castro de San Cristóbal | unresolved/false friend risk | San Sadurniño NNSS contains a San Cristóbal chapel, not a castro match. |
| Tralocastro, San Xiao de Lamas | different-site name collision | Ferrol/Esmelle Tralocastro is a strong official site, but it is not the San Sadurniño/Lamas disappeared entry. |
| Castro de As Filgueiras | classical/no coordinate | Valdoviño official/PBA sources contain other Meirás sites, but no exact As Filgueiras match. |

## Operational Output

Detailed row-level decisions are in:

`data/review-queues/remaining_geocoding_source_audit.tsv`

## Next Manual Move

1. In QGIS, inspect `tra-ferrol-ga15036005` against the classical Ferreiros row. If they are the same site, merge/drop `tra-ferrol-ferreiros`; if not, keep Ferreiros blocked.
2. In QGIS, inspect the Bardaos PBA candidate against `tra-san-sadurnino-fraga`. If the classical Fraga entry is only a duplicate/toponymic variant, merge/drop it; if not, keep it blocked.
3. Keep the other seven out of train/val/test until a stronger source appears.
