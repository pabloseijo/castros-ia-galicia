.PHONY: dataset qgis-review annotations verify clean

dataset:
	python3 scripts/build_castros_ia_dataset.py

qgis-review: dataset
	python3 scripts/build_castros_qgis_review_package.py

annotations: qgis-review
	python3 scripts/build_annotation_workspace.py

verify:
	python3 -m py_compile scripts/build_castros_ia_dataset.py scripts/build_castros_qgis_review_package.py scripts/build_annotation_workspace.py scripts/verify_annotation_workspace.py
	python3 scripts/build_castros_ia_dataset.py
	python3 scripts/build_castros_qgis_review_package.py
	python3 scripts/build_annotation_workspace.py
	python3 scripts/verify_annotation_workspace.py

clean:
	rm -rf data/processed/castros-trasancos-mvp data/qgis-review data/annotations
