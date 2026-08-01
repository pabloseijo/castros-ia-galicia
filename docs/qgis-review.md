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
5. Usar `remaining_equivalence_candidates`, si existe, para decidir posibles duplicados de filas clásicas bloqueadas.
6. Geocodificar manualmente o descartar lo que siga bloqueado tras PBA.
7. Ajustar buffers de 120 m a croa/muralla/recinto cuando sea visible.
8. Aceptar negativos solo si PNOA/LiDAR no muestra forma arqueológica plausible.
9. Dibujar positivos revisados en `labels_reviewed`.
10. Dibujar negativos aceptados en `negative_areas_reviewed`.
11. Añadir coordenadas corregidas en `geocoded_sites_reviewed`.
12. Marcar decisiones en `site_review_decisions` y `negative_review_decisions`.

Los buffers generados no son etiquetas finales.
Los puntos PBA son candidatos oficiales de localización/reconciliación; tampoco son etiquetas finales.
Los puntos de equivalencia posible solo sirven para decidir si una fila clásica debe fusionarse o descartarse frente a un registro más fuerte.

## Revisión De Errores Weak-Label

Para revisar los errores de la fusión RGB+relieve por carriles, abrir:

`data/weak-label-error-review-workspace-v1/weak_label_error_review_workspace_v1.gpkg`

Capas recomendadas:

1. `p0_unique_first_pass`
2. `lane_mamoa_false_positive`
3. `lane_mamoa_specialist_positive`
4. `lane_morphology_rescue`
5. `unique_error_review_points`

Campos clave:

- `review_lane`: tipo de fallo o rescate.
- `duplicate_count`: si el mismo punto aparece en más de una cola.
- `suggested_taxonomy`: taxonomía inicial, no verdad final.
- `specialist_rank`: ranking del especialista castro-vs-mámoa.
- `fusion_rank`: ranking de la fusión principal.
- `max_safety_rank`: ranking de rescate morfológico.

La tabla `error_review_decisions` es una plantilla de decisión. No convierte automáticamente un punto en etiqueta de entrenamiento: las etiquetas fuertes siguen entrando por `labels_reviewed` y `negative_areas_reviewed`.

## Campos recomendados

En `labels_reviewed`:

- `label_class`: `castro`, `croa`, `recinto`, `muralla`, `foso`, `uncertain`.
- `label_geometry`: `manual_polygon`, `adjusted_buffer`, `visible_boundary`, `approximate_boundary`.
- `confidence`: `high`, `medium`, `low`.
- `review_status`: `accepted`, `needs_followup`, `rejected`.
- `source_basis`: `pnoa`, `lidar`, `catalog`, `field`, o combinación separada por `+`.

Para exportar entrenamiento, los positivos aceptados deben tener cubiertos: `label_id`, `site_id`, `primary_name`, `final_split`, `label_class`, `label_geometry`, `confidence`, `source_basis`, `reviewed_by` y `reviewed_date`.

En `negative_areas_reviewed`:

- `negative_type`: `agricultural`, `forestry`, `road_cut`, `quarry`, `natural_hill`, `urban`, `unclear`.
- `review_status`: `accepted` solo si no parece forma arqueológica plausible.

Para exportar entrenamiento, los negativos aceptados deben tener cubiertos: `negative_label_id`, `final_split`, `negative_type`, `confidence`, `source_basis`, `reviewed_by` y `reviewed_date`.

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

Segunda pasada de bloqueos:

`reports/remaining_geocoding_source_audit.md`

Su capa QGIS asociada, si existe, es `remaining_equivalence_candidates`.

## Después de revisar

Cuando haya polígonos aceptados:

```bash
make training-manifest
```

Si sigue saliendo `training_status=blocked`, falta al menos un positivo aceptado, un negativo aceptado o metadatos obligatorios en alguna geometría aceptada.
