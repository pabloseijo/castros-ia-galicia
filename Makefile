.PHONY: dataset qgis-review annotations reports raster-prep pba-unlock pba-review training-manifest webmap env-check sync-wiki verify clean

dataset:
	python3 scripts/build_castros_ia_dataset.py

qgis-review: dataset
	python3 scripts/build_castros_qgis_review_package.py

annotations: qgis-review
	python3 scripts/build_annotation_workspace.py

reports: annotations
	python3 scripts/build_review_reports.py

raster-prep: qgis-review
	python3 scripts/build_raster_tile_manifest.py

pba-unlock:
	python3 scripts/query_pba_catalog_unlock.py

pba-review: pba-unlock qgis-review annotations reports raster-prep webmap

training-manifest: annotations
	python3 scripts/export_training_manifest.py

webmap: qgis-review
	python3 scripts/build_web_review_map.py

env-check:
	python3 scripts/check_environment.py

sync-wiki: qgis-review
	python3 scripts/sync_wiki_exports.py

verify:
	python3 -m py_compile scripts/build_castros_ia_dataset.py scripts/build_castros_qgis_review_package.py scripts/build_annotation_workspace.py scripts/verify_annotation_workspace.py scripts/build_review_reports.py scripts/build_raster_tile_manifest.py scripts/query_pba_catalog_unlock.py scripts/export_training_manifest.py scripts/build_web_review_map.py scripts/check_environment.py scripts/sync_wiki_exports.py
	python3 scripts/build_castros_ia_dataset.py
	python3 scripts/build_castros_qgis_review_package.py
	python3 scripts/build_annotation_workspace.py
	python3 scripts/verify_annotation_workspace.py
	python3 scripts/build_review_reports.py
	python3 scripts/build_raster_tile_manifest.py
	python3 scripts/export_training_manifest.py
	python3 scripts/build_web_review_map.py
	python3 scripts/check_environment.py

clean:
	rm -rf data/processed/castros-trasancos-mvp data/qgis-review data/annotations data/review-queues data/raster-prep data/training reports/*.md webmap/index.html
