.PHONY: dataset qgis-review verify clean

dataset:
	python3 scripts/build_castros_ia_dataset.py

qgis-review: dataset
	python3 scripts/build_castros_qgis_review_package.py

verify:
	python3 -m py_compile scripts/build_castros_ia_dataset.py scripts/build_castros_qgis_review_package.py
	python3 scripts/build_castros_ia_dataset.py
	python3 scripts/build_castros_qgis_review_package.py

clean:
	rm -rf data/processed/castros-trasancos-mvp data/qgis-review
