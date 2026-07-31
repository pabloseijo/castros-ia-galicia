# Revisión QGIS

Abrir:

`data/qgis-review/castros_trasancos_qgis_review.gpkg`

Y abrir también el workspace editable:

`data/annotations/castros_annotations.gpkg`

Orden de trabajo:

1. Revisar tareas `P0`.
2. Comprobar O Val como holdout: Monte do Castro, Quintá, A Pedreira y Vilasuso.
3. Resolver Pena Grande/Lagoa como conflicto castro/cercado neolítico.
4. Usar `pba_geocoding_candidates`, si existe, para geocodificar/reconciliar filas sin coordenadas.
5. Geocodificar manualmente o descartar lo que siga bloqueado tras PBA.
6. Ajustar buffers de 120 m a croa/muralla/recinto cuando sea visible.
7. Aceptar negativos solo si PNOA/LiDAR no muestra forma arqueológica plausible.
8. Dibujar positivos revisados en `labels_reviewed`.
9. Dibujar negativos aceptados en `negative_areas_reviewed`.
10. Añadir coordenadas corregidas en `geocoded_sites_reviewed`.
11. Marcar decisiones en `site_review_decisions` y `negative_review_decisions`.

Los buffers generados no son etiquetas finales.
Los puntos PBA son candidatos oficiales de localización/reconciliación; tampoco son etiquetas finales.

## Campos recomendados

En `labels_reviewed`:

- `label_class`: `castro`, `croa`, `recinto`, `muralla`, `foso`, `uncertain`.
- `label_geometry`: `manual_polygon`, `adjusted_buffer`, `visible_boundary`, `approximate_boundary`.
- `confidence`: `high`, `medium`, `low`.
- `review_status`: `accepted`, `needs_followup`, `rejected`.
- `source_basis`: `pnoa`, `lidar`, `catalog`, `field`, o combinación separada por `+`.

En `negative_areas_reviewed`:

- `negative_type`: `agricultural`, `forestry`, `road_cut`, `quarry`, `natural_hill`, `urban`, `unclear`.
- `review_status`: `accepted` solo si no parece forma arqueológica plausible.

## Colas generadas

Para entrar en faena sin perderse:

- `data/review-queues/p0_blockers.tsv`
- `data/review-queues/o_val_holdout.tsv`
- `data/review-queues/needs_geocoding.tsv`
- `data/review-queues/p1_training_candidates.tsv`
- `data/review-queues/p2_reconciliation.tsv`

Reporte legible:

`reports/review_status.md`

Desbloqueo PBA:

```bash
make pba-review
```

Ese comando consulta el PBA/Xunta, actualiza `reports/pba_catalog_unlock.md` y regenera el paquete QGIS con `pba_geocoding_candidates`.

## Después de revisar

Cuando haya polígonos aceptados:

```bash
make training-manifest
```

Si sigue saliendo `training_status=blocked`, falta al menos un positivo aceptado o un negativo aceptado.
