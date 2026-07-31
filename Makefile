.PHONY: dataset qgis-review annotations annotations-reset annotation-backup reports raster-prep pnoa-preview-index pnoa-chips viladonga-audit viladonga-pnoa-chips viladonga-wcs-dem viladonga-lidar-derivatives viladonga-relief-wcs viladonga-pilot pba-unlock pba-review training-manifest webmap env-check repo-drift sync-wiki agent-list agent-run agent-run-one agent-systemd verify clean

dataset:
	python3 scripts/build_castros_ia_dataset.py

qgis-review: dataset
	python3 scripts/build_castros_qgis_review_package.py

annotations: qgis-review
	python3 scripts/build_annotation_workspace.py

annotations-reset: qgis-review
	python3 scripts/build_annotation_workspace.py --force

annotation-backup:
	python3 scripts/backup_annotation_workspace.py

reports: annotations
	python3 scripts/build_review_reports.py

raster-prep: qgis-review
	python3 scripts/build_raster_tile_manifest.py

pnoa-preview-index:
	python3 scripts/build_pnoa_preview_index.py --smoke-test 1

pnoa-chips:
	python3 scripts/export_reviewed_pnoa_chips.py

viladonga-audit:
	python3 scripts/audit_viladonga_pilot.py

viladonga-pnoa-chips:
	python3 scripts/export_viladonga_pnoa_chips.py

viladonga-wcs-dem:
	python3 scripts/fetch_viladonga_mdt_wcs.py

viladonga-lidar-derivatives:
	python3 scripts/build_viladonga_lidar_derivatives.py

viladonga-relief-wcs: viladonga-wcs-dem
	python3 scripts/build_viladonga_lidar_derivatives.py --dem data/viladonga-pilot/lidar/viladonga_mdt5_wcs.tif

viladonga-pilot: viladonga-audit viladonga-relief-wcs viladonga-pnoa-chips

pba-unlock:
	python3 scripts/query_pba_catalog_unlock.py

pba-review: pba-unlock qgis-review annotations reports raster-prep webmap

training-manifest: annotations
	python3 scripts/export_training_manifest.py

webmap: qgis-review
	python3 scripts/build_web_review_map.py

env-check:
	python3 scripts/check_environment.py

repo-drift:
	python3 scripts/check_repo_drift.py

sync-wiki: qgis-review
	python3 scripts/sync_wiki_exports.py

agent-list:
	python3 scripts/run_raspberry_agents.py --list

agent-run:
	python3 scripts/run_raspberry_agents.py --run-enabled

agent-run-one:
	python3 scripts/run_raspberry_agents.py --agent "$(AGENT)"

agent-systemd:
	python3 scripts/render_raspberry_systemd_units.py --out-dir ops/raspberry/systemd

verify:
	python3 -m py_compile scripts/build_castros_ia_dataset.py scripts/build_castros_qgis_review_package.py scripts/build_annotation_workspace.py scripts/verify_annotation_workspace.py scripts/build_review_reports.py scripts/build_raster_tile_manifest.py scripts/build_pnoa_preview_index.py scripts/export_reviewed_pnoa_chips.py scripts/audit_viladonga_pilot.py scripts/export_viladonga_pnoa_chips.py scripts/fetch_viladonga_mdt_wcs.py scripts/build_viladonga_lidar_derivatives.py scripts/query_pba_catalog_unlock.py scripts/export_training_manifest.py scripts/build_web_review_map.py scripts/check_environment.py scripts/check_repo_drift.py scripts/backup_annotation_workspace.py scripts/sync_wiki_exports.py scripts/run_raspberry_agents.py scripts/render_raspberry_systemd_units.py
	python3 scripts/build_castros_ia_dataset.py
	python3 scripts/build_castros_qgis_review_package.py
	python3 scripts/build_annotation_workspace.py
	python3 scripts/verify_annotation_workspace.py
	python3 scripts/build_review_reports.py
	python3 scripts/build_raster_tile_manifest.py
	python3 scripts/build_pnoa_preview_index.py --smoke-test 1
	python3 scripts/export_training_manifest.py
	python3 scripts/export_reviewed_pnoa_chips.py
	python3 scripts/build_web_review_map.py
	python3 scripts/check_environment.py

clean:
	rm -rf data/processed/castros-trasancos-mvp data/qgis-review data/annotations data/review-queues data/raster-prep data/training reports/*.md webmap/index.html
