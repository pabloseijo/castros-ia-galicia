# Auditoría científica de metodología

Fecha: 2026-07-31

## Veredicto

El proyecto va por el camino correcto si se entiende como pipeline de revisión y priorización, no como sistema automático de descubrimiento. La literatura respalda tres decisiones ya tomadas: empezar por LiDAR/relieve y QGIS, mantener humanos en el bucle, y no entrenar antes de tener etiquetas revisadas.

El mayor ajuste necesario era evitar fuga espacial entre entrenamiento y test. Ya queda corregido: el split principal pasa a ser por municipio, no pseudoaleatorio.

## Cambio aplicado tras la auditoría

Antes:

- `train`/`val`/`test` se asignaban por hash determinista de `site_id`.
- Eso podía poner sitios cercanos en entrenamiento y prueba.

Ahora:

- `train`: Ferrol, Valdoviño y Neda.
- `val`: San Sadurniño.
- `test`: Narón no-O-Val.
- `test_o_val`: O Val como holdout narrativo separado.
- `review_only`: dañados, conflictivos, web no reconciliado, sin coordenadas o baja confianza.

Resultado actual:

- `train`: 25.
- `val`: 6.
- `test`: 8.
- `test_o_val`: 3.
- `review_only`: 86.

## Qué estamos haciendo bien

| Área | Diagnóstico | Base científica |
|---|---|---|
| Humano en el bucle | Correcto. La salida debe ser revisable en QGIS, no "hallazgos" automáticos. | Casini et al. 2023; Verschoof-van der Vaart y Lambers 2022 |
| LiDAR primero | Correcto. Para castros, la forma del terreno es más defendible que Sentinel-2 como señal principal. | Hesse 2010; Doneus 2013; Štular et al. 2012; Vinci et al. 2024 |
| Derivados de relieve | Correcto, pero aún pendiente de ejecutar. Hay que generar hillshade, slope, openness/SVF, LRM/MSRM. | Hesse 2010; Doneus 2013; Kokalj et al. 2023 |
| Dataset multimodal | Correcto como horizonte. Para MVP, LiDAR/PNOA debe mandar y Sentinel ser auxiliar. | Berganzo-Besga et al. 2021; Canedo et al. 2024; Kokalj et al. 2023 |
| Polígonos/máscaras | Pendiente. Los puntos y buffers no bastan para entrenar bien. | Kokalj et al. 2023; Canedo et al. 2024; Bonhage et al. 2021 |
| Negativos difíciles | Correcto como idea, pero deben revisarse visualmente. No basta con puntos lejos de positivos. | Fiorucci et al. 2022; Landauer et al. 2025 |
| Holdout O Val | Correcto. Protege el caso narrativo y evita sobreajuste local. | Buenas prácticas CV arqueológica; evaluación "in the wild" |
| Publicación de candidatos | Correcto mantener cautela. Las predicciones/candidatos no deben publicarse como yacimientos. | Pansoni et al. 2023; Tiribelli et al. 2024; Kokalj et al. 2023 |

## Qué falta antes de entrenar

1. Revisar `data/qgis-review/castros_trasancos_qgis_review.gpkg` en QGIS.
2. Crear una capa nueva `labels_reviewed` con geometrías humanas.
3. Convertir buffers provisionales en polígonos o descartarlos.
4. Revisar negativos difíciles contra PNOA/LiDAR.
5. Descargar PNOA/LiDAR solo para ventanas útiles.
6. Generar derivados: hillshade, slope, positive openness, sky-view factor, LRM/MSRM.
7. Crear recortes raster 512 m y máscaras/bounding boxes.
8. Entrenar primero baseline no deep learning y luego YOLO/U-Net/Mask R-CNN si el dataset lo permite.
9. Evaluar con IoU/mAP/recall y con revisión arqueológica de falsos positivos.
10. No publicar coordenadas de candidatos no verificados.

## Matriz de diseño

| Componente | Estado actual | Juicio | Acción |
|---|---|---|---|
| Inventario de sitios | 128 filas | Bien para MVP | Mantener y depurar |
| Coordenadas | 91 puntos | Bien para revisión, insuficiente para entrenamiento | Resolver 37 geocoding tasks |
| Split | Espacial por municipio | Mejorado | Mantener hasta ampliar corpus |
| O Val | Holdout `test_o_val` | Muy bien | No entrenar con O Val en v0 |
| Buffers | 42 semillas de 120 m | Útiles, no etiquetas | Ajustar manualmente |
| Ventanas raster | 42 ventanas de 512 m | Bien como preselección | Descargar rasters tras revisión |
| Negativos | 160 puntos generados | Útiles solo tras revisión | Convertir en negativos confirmados |
| Métricas | No implementadas | Pendiente | Diseñar IoU/mAP/recall + revisión humana |
| Modelo | No entrenado | Correcto | No entrenar antes de etiquetas |

## Papers contrastados

| Paper | Lectura para el proyecto |
|---|---|
| Berganzo-Besga, Orengo y Lumbreras (2026), "Best practices for the application of computer vision-based machine learning in archaeology" | Refuerza dataset auditado, separación train/test y evitar promesas fuertes. |
| Orengo, Berganzo-Besga y Lumbreras (2026), "Theory and practice of artificial intelligence in archaeology" | Marco general para formularlo como asistencia arqueológica, no sustitución. |
| Berganzo-Besga et al. (2021), "Hybrid MSRM-Based Deep Learning and Multitemporal Sentinel-2..." | El precedente gallego/noroeste más importante: MSRM/LiDAR + Sentinel auxiliar. |
| Canedo et al. (2024), "Automated Detection of Hillforts..." | Referencia directa para castros/hillforts y segmentación multimodal. |
| Landauer et al. (2025), "Europe Wide Hillfort Search" | Refuerza escalado, negativos y evaluación espacial. |
| Hesse (2010), "LiDAR-derived Local Relief Models" | Justifica LRM como derivado esencial. |
| Doneus (2013), "Openness as Visualization Technique..." | Justifica positive/negative openness y lectura interpretativa del MDT. |
| Štular et al. (2012), "Visualization of lidar-derived relief models..." | Obliga a comparar varias visualizaciones de relieve. |
| Vinci et al. (2024/2025), "LiDAR Applications in Archaeology: A Systematic Review" | Confirma LiDAR como columna vertebral del proyecto. |
| Fiorucci et al. (2022), "Deep Learning for Archaeological Object Detection on LiDAR" | Importante para métricas específicas, no solo accuracy. |
| Verschoof-van der Vaart y Lambers (2019), "Learning to Look at LiDAR" | Precedente R-CNN + GIS para prospección. |
| Verschoof-van der Vaart et al. (2020), "Combining Deep Learning and Location-Based Ranking..." | Útil para priorizar candidatos en vez de vender predicciones binarias. |
| Verschoof-van der Vaart y Lambers (2022), "Applying automated object detection in archaeological practice" | Recuerda que el modelo debe funcionar "in the wild". |
| Trier et al. (2021), "Automated mapping of cultural heritage in Norway..." | Precedente Faster R-CNN con LiDAR institucional. |
| Bonhage et al. (2021), "Modified Mask R-CNN..." | Modelo para pasar de detección a segmentación/perímetros. |
| Guyot et al. (2021), "Combined Detection and Segmentation..." | Refuerza combinar detección y segmentación en LiDAR. |
| Kokalj et al. (2023), "Machine learning-ready remote sensing data for Maya archaeology" | Ejemplo fuerte de dataset multimodal con máscaras manuales y restricciones de localización. |
| Casini et al. (2023), "A human-AI collaboration workflow..." | Justifica el flujo QGIS/humano antes y después del modelo. |
| Argyrou y Agapiou (2022), "A Review of Artificial Intelligence and Remote Sensing..." | Revisión general de IA + teledetección arqueológica. |
| Pansoni et al. (2023), "Artificial Intelligence and Cultural Heritage..." | Marco ético para no publicar candidatos sensibles sin control. |
| Tiribelli et al. (2024), "Ethics of Artificial Intelligence for Cultural Heritage" | Refuerzo ético para uso responsable de IA patrimonial. |

## Conclusión operativa

El proyecto no debe avanzar a entrenamiento todavía. El siguiente paso correcto es QGIS: convertir puntos y buffers en geometrías revisadas. Después vendrá raster, derivados de relieve y baseline. Solo entonces tiene sentido hablar de modelo.
