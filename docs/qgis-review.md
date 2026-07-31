# Revisión QGIS

Abrir:

`data/qgis-review/castros_trasancos_qgis_review.gpkg`

Y abrir también el workspace editable:

`data/annotations/castros_annotations.gpkg`

Orden de trabajo:

1. Revisar tareas `P0`.
2. Comprobar O Val como holdout: Quintá, A Pedreira y Vilasuso.
3. Resolver Pena Grande/Lagoa como conflicto castro/cercado neolítico.
4. Geocodificar filas sin coordenadas o descartarlas del MVP geoespacial.
5. Ajustar buffers de 120 m a croa/muralla/recinto cuando sea visible.
6. Aceptar negativos solo si PNOA/LiDAR no muestra forma arqueológica plausible.
7. Dibujar positivos revisados en `labels_reviewed`.
8. Dibujar negativos aceptados en `negative_areas_reviewed`.
9. Añadir coordenadas corregidas en `geocoded_sites_reviewed`.
10. Marcar decisiones en `site_review_decisions` y `negative_review_decisions`.

Los buffers generados no son etiquetas finales.

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
