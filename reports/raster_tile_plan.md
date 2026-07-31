# Raster tile preparation plan

Generated: 2026-07-31

- Candidate windows: 45
- Window side: 512 m
- CRS for raster processing: EPSG:25829/UTM 29N
- Download status: pending QGIS review

## By split

- test: 10
- test_o_val: 4
- train: 25
- val: 6

## By municipality

- Ferrol: 9
- Narón: 14
- Neda: 2
- San Sadurniño: 6
- Valdoviño: 14

## Rule

Do not download/process rasters for a window until its source site has an accepted or follow-up decision in the annotation workspace.
