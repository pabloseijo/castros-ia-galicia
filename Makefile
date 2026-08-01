GEO_PYTHON ?= .venv-geo/bin/python

.PHONY: dataset qgis-review annotations annotations-reset annotation-backup reports raster-prep pnoa-preview-index pnoa-chips viladonga-audit viladonga-cnig-lidar-candidates viladonga-pnoa-chips viladonga-mask-quality viladonga-shape-baseline viladonga-relief-shape-baseline viladonga-radial-relief-profile viladonga-wcs-dem viladonga-lidar-derivatives viladonga-relief-wcs viladonga-pilot pba-unlock pba-review morphology-bank morphology-autoreview morphology-visual-signals weak-label-splits weak-label-chips-smoke weak-label-chips-holdouts weak-label-chips-val weak-label-chips-test weak-label-chips-train-mini weak-label-chips-train weak-label-rgb-baseline-mini weak-label-rgb-baseline-full weak-label-relief-holdouts weak-label-relief-val weak-label-relief-test weak-label-relief-train-mini weak-label-relief-train weak-label-relief-baseline-holdouts weak-label-relief-baseline-val weak-label-relief-baseline-test weak-label-relief-baseline-train-mini weak-label-relief-baseline-train weak-label-relief-score-variants weak-label-relief-coverage-policy weak-label-rgb-relief-baseline-mini weak-label-rgb-relief-baseline-full weak-label-priority-blend weak-label-priority-blend-full weak-label-error-review weak-label-error-review-full weak-label-error-review-figures weak-label-error-review-workspace weak-label-p0-visual-dossier weak-label-p0-decision-seed weak-label-p0-boundary-proposals weak-label-castro-mamoa-specialist weak-label-castro-mamoa-specialist-full o-val-relief-diagnostics training-manifest webmap env-check repo-drift sync-wiki agent-list agent-run agent-run-one agent-systemd verify clean

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

viladonga-cnig-lidar-candidates:
	python3 scripts/query_viladonga_cnig_lidar.py

viladonga-pnoa-chips:
	python3 scripts/export_viladonga_pnoa_chips.py

viladonga-mask-quality:
	python3 scripts/evaluate_viladonga_mask_quality.py

viladonga-shape-baseline:
	python3 scripts/evaluate_viladonga_pnoa_shape_baseline.py

viladonga-relief-shape-baseline:
	python3 scripts/evaluate_viladonga_relief_shape_baseline.py

viladonga-radial-relief-profile:
	python3 scripts/evaluate_viladonga_radial_relief_profile.py

viladonga-wcs-dem:
	python3 scripts/fetch_viladonga_mdt_wcs.py

viladonga-lidar-derivatives:
	python3 scripts/build_viladonga_lidar_derivatives.py

viladonga-relief-wcs: viladonga-wcs-dem
	python3 scripts/build_viladonga_lidar_derivatives.py --dem data/viladonga-pilot/lidar/viladonga_mdt5_wcs.tif

viladonga-pilot: viladonga-audit viladonga-relief-wcs viladonga-pnoa-chips viladonga-mask-quality viladonga-shape-baseline viladonga-relief-shape-baseline viladonga-radial-relief-profile

pba-unlock:
	python3 scripts/query_pba_catalog_unlock.py

pba-review: pba-unlock qgis-review annotations reports raster-prep webmap

morphology-bank:
	python3 scripts/build_morphology_control_bank.py

morphology-autoreview: morphology-bank
	python3 scripts/build_morphology_autoreview_package.py

morphology-visual-signals:
	$(GEO_PYTHON) scripts/evaluate_morphology_autoreview_visual_signals.py
	ogr2ogr -f GPKG data/morphology-autoreview-v1/morphology_autoreview_v1_visual_signals.gpkg data/morphology-autoreview-v1/control_set_v1_visual_scores.geojson -nln control_set_v1_visual_scores -overwrite

weak-label-splits: morphology-bank
	$(GEO_PYTHON) scripts/build_weak_label_splits.py
	ogr2ogr -f GPKG data/weak-label-splits-v1/weak_label_splits_v1.gpkg data/weak-label-splits-v1/weak_label_points.geojson -nln weak_label_points -overwrite

weak-label-chips-smoke:
	$(GEO_PYTHON) scripts/export_weak_label_chips.py --splits train,val,test,test_trasancos,test_o_val --per-split 4 --workers 10 --out-manifest data/weak-label-splits-v1/weak_label_chip_export_smoke.tsv --report reports/weak_label_chip_export_smoke.md

weak-label-chips-holdouts:
	$(GEO_PYTHON) scripts/export_weak_label_chips.py --splits test_o_val,test_trasancos --workers 10 --out-manifest data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv --report reports/weak_label_chip_export_holdouts.md

weak-label-chips-val:
	$(GEO_PYTHON) scripts/export_weak_label_chips.py --splits val --workers 10 --out-manifest data/weak-label-splits-v1/weak_label_chip_export_val.tsv --report reports/weak_label_chip_export_val.md

weak-label-chips-test:
	$(GEO_PYTHON) scripts/export_weak_label_chips.py --splits test --workers 10 --out-manifest data/weak-label-splits-v1/weak_label_chip_export_test.tsv --report reports/weak_label_chip_export_test.md

weak-label-chips-train-mini:
	$(GEO_PYTHON) scripts/export_weak_label_chips.py --splits train --per-split 1000 --workers 10 --out-manifest data/weak-label-splits-v1/weak_label_chip_export_train_mini.tsv --report reports/weak_label_chip_export_train_mini.md

weak-label-chips-train:
	$(GEO_PYTHON) scripts/export_weak_label_chips.py --splits train --workers 10 --out-manifest data/weak-label-splits-v1/weak_label_chip_export_train.tsv --report reports/weak_label_chip_export_train.md

weak-label-rgb-baseline-mini:
	$(GEO_PYTHON) scripts/train_weak_label_rgb_baseline.py

weak-label-rgb-baseline-full:
	$(GEO_PYTHON) scripts/train_weak_label_rgb_baseline.py --train-manifest data/weak-label-splits-v1/weak_label_chip_export_train.tsv --eval-manifest data/weak-label-splits-v1/weak_label_chip_export_val.tsv --eval-manifest data/weak-label-splits-v1/weak_label_chip_export_test.tsv --eval-manifest data/weak-label-splits-v1/weak_label_chip_export_holdouts.tsv --artifact-prefix weak_label_rgb_baseline_full --report reports/weak_label_rgb_baseline_full_v1.md

weak-label-relief-holdouts:
	$(GEO_PYTHON) scripts/export_weak_label_relief_wcs.py --workers 6 --wcs-parallel 4

weak-label-relief-val:
	$(GEO_PYTHON) scripts/export_weak_label_relief_wcs.py --input data/weak-label-splits-v1/weak_label_chip_export_val.tsv --out-manifest data/weak-label-relief-v1/weak_label_relief_wcs_val.tsv --report reports/weak_label_relief_wcs_val.md --workers 6 --wcs-parallel 4

weak-label-relief-test:
	$(GEO_PYTHON) scripts/export_weak_label_relief_wcs.py --input data/weak-label-splits-v1/weak_label_chip_export_test.tsv --out-manifest data/weak-label-relief-v1/weak_label_relief_wcs_test.tsv --report reports/weak_label_relief_wcs_test.md --workers 6 --wcs-parallel 4

weak-label-relief-train-mini:
	$(GEO_PYTHON) scripts/export_weak_label_relief_wcs.py --input data/weak-label-splits-v1/weak_label_chip_export_train_mini.tsv --out-manifest data/weak-label-relief-v1/weak_label_relief_wcs_train_mini.tsv --report reports/weak_label_relief_wcs_train_mini.md --workers 6 --wcs-parallel 4

weak-label-relief-train:
	$(GEO_PYTHON) scripts/export_weak_label_relief_wcs.py --input data/weak-label-splits-v1/weak_label_chip_export_train.tsv --out-manifest data/weak-label-relief-v1/weak_label_relief_wcs_train.tsv --report reports/weak_label_relief_wcs_train.md --workers 6 --wcs-parallel 4

weak-label-relief-baseline-holdouts:
	$(GEO_PYTHON) scripts/evaluate_weak_label_relief_baseline.py

weak-label-relief-baseline-val:
	$(GEO_PYTHON) scripts/evaluate_weak_label_relief_baseline.py --relief-manifest data/weak-label-relief-v1/weak_label_relief_wcs_val.tsv --dataset-name val --report reports/weak_label_relief_baseline_val.md

weak-label-relief-baseline-test:
	$(GEO_PYTHON) scripts/evaluate_weak_label_relief_baseline.py --relief-manifest data/weak-label-relief-v1/weak_label_relief_wcs_test.tsv --dataset-name test --rgb-metrics data/weak-label-baseline-v1/weak_label_rgb_baseline_full_metrics.tsv --report reports/weak_label_relief_baseline_test.md

weak-label-relief-baseline-train-mini:
	$(GEO_PYTHON) scripts/evaluate_weak_label_relief_baseline.py --relief-manifest data/weak-label-relief-v1/weak_label_relief_wcs_train_mini.tsv --dataset-name train_mini --report reports/weak_label_relief_baseline_train_mini.md

weak-label-relief-baseline-train:
	$(GEO_PYTHON) scripts/evaluate_weak_label_relief_baseline.py --relief-manifest data/weak-label-relief-v1/weak_label_relief_wcs_train.tsv --dataset-name train --rgb-metrics data/weak-label-baseline-v1/weak_label_rgb_baseline_full_metrics.tsv --report reports/weak_label_relief_baseline_train.md

weak-label-relief-score-variants:
	$(GEO_PYTHON) scripts/evaluate_weak_label_relief_score_variants.py

weak-label-relief-coverage-policy:
	$(GEO_PYTHON) scripts/build_weak_label_relief_coverage_policy.py

weak-label-rgb-relief-baseline-mini:
	$(GEO_PYTHON) scripts/train_weak_label_rgb_relief_baseline.py

weak-label-rgb-relief-baseline-full:
	$(GEO_PYTHON) scripts/train_weak_label_rgb_relief_baseline.py --rgb-features data/weak-label-baseline-v1/weak_label_rgb_baseline_full_features.tsv --rgb-metrics data/weak-label-baseline-v1/weak_label_rgb_baseline_full_metrics.tsv --relief-features data/weak-label-relief-v1/weak_label_relief_features_train.tsv --relief-features data/weak-label-relief-v1/weak_label_relief_features_val.tsv --relief-features data/weak-label-relief-v1/weak_label_relief_features_test.tsv --relief-features data/weak-label-relief-v1/weak_label_relief_features_holdouts.tsv --relief-metrics data/weak-label-relief-v1/weak_label_relief_metrics_train.tsv --relief-metrics data/weak-label-relief-v1/weak_label_relief_metrics_val.tsv --relief-metrics data/weak-label-relief-v1/weak_label_relief_metrics_test.tsv --relief-metrics data/weak-label-relief-v1/weak_label_relief_metrics_holdouts.tsv --train-dataset train --artifact-prefix weak_label_rgb_relief_full --report reports/weak_label_rgb_relief_baseline_full_v1.md

weak-label-priority-blend:
	$(GEO_PYTHON) scripts/evaluate_weak_label_priority_blend.py

weak-label-priority-blend-full:
	$(GEO_PYTHON) scripts/evaluate_weak_label_priority_blend.py --features data/weak-label-fusion-v1/weak_label_rgb_relief_full_features.tsv --scores data/weak-label-fusion-v1/weak_label_rgb_relief_full_scores.tsv --fusion-metrics data/weak-label-fusion-v1/weak_label_rgb_relief_full_metrics.tsv --artifact-prefix weak_label_priority_blend_full --report reports/weak_label_priority_blend_full_v1.md

weak-label-error-review:
	$(GEO_PYTHON) scripts/build_weak_label_error_review_queue.py

weak-label-error-review-full:
	$(GEO_PYTHON) scripts/build_weak_label_error_review_queue.py --fusion-scores data/weak-label-fusion-v1/weak_label_rgb_relief_full_scores.tsv --priority-scores data/weak-label-fusion-v1/weak_label_priority_blend_full_scores.tsv --specialist-scores data/weak-label-fusion-v1/weak_label_castro_mamoa_specialist_full_scores.tsv --artifact-prefix weak_label_error_review_queue_full --report reports/weak_label_error_review_queue_full_v1.md

weak-label-error-review-figures:
	$(GEO_PYTHON) scripts/build_weak_label_error_review_figures.py

weak-label-error-review-workspace:
	$(GEO_PYTHON) scripts/build_weak_label_error_review_workspace.py

weak-label-p0-visual-dossier: weak-label-error-review-workspace
	$(GEO_PYTHON) scripts/build_weak_label_p0_visual_dossier.py

weak-label-p0-decision-seed: weak-label-p0-visual-dossier
	$(GEO_PYTHON) scripts/build_weak_label_p0_decision_seed.py

weak-label-p0-boundary-proposals: weak-label-p0-decision-seed
	$(GEO_PYTHON) scripts/build_weak_label_p0_boundary_proposals.py

weak-label-castro-mamoa-specialist:
	$(GEO_PYTHON) scripts/train_weak_label_castro_mamoa_specialist.py

weak-label-castro-mamoa-specialist-full:
	$(GEO_PYTHON) scripts/train_weak_label_castro_mamoa_specialist.py --features data/weak-label-fusion-v1/weak_label_rgb_relief_full_features.tsv --fusion-scores data/weak-label-fusion-v1/weak_label_rgb_relief_full_scores.tsv --priority-scores data/weak-label-fusion-v1/weak_label_priority_blend_full_scores.tsv --train-dataset train --artifact-prefix weak_label_castro_mamoa_specialist_full --report reports/weak_label_castro_mamoa_specialist_full_v1.md

o-val-relief-diagnostics:
	$(GEO_PYTHON) scripts/build_o_val_relief_diagnostics.py

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
	python3 -m py_compile scripts/build_castros_ia_dataset.py scripts/build_castros_qgis_review_package.py scripts/build_annotation_workspace.py scripts/verify_annotation_workspace.py scripts/build_review_reports.py scripts/build_raster_tile_manifest.py scripts/build_pnoa_preview_index.py scripts/export_reviewed_pnoa_chips.py scripts/audit_viladonga_pilot.py scripts/query_viladonga_cnig_lidar.py scripts/export_viladonga_pnoa_chips.py scripts/evaluate_viladonga_mask_quality.py scripts/evaluate_viladonga_pnoa_shape_baseline.py scripts/evaluate_viladonga_relief_shape_baseline.py scripts/evaluate_viladonga_radial_relief_profile.py scripts/fetch_viladonga_mdt_wcs.py scripts/build_viladonga_lidar_derivatives.py scripts/query_pba_catalog_unlock.py scripts/build_morphology_control_bank.py scripts/build_morphology_autoreview_package.py scripts/evaluate_morphology_autoreview_visual_signals.py scripts/build_weak_label_splits.py scripts/export_weak_label_chips.py scripts/train_weak_label_rgb_baseline.py scripts/export_weak_label_relief_wcs.py scripts/evaluate_weak_label_relief_baseline.py scripts/evaluate_weak_label_relief_score_variants.py scripts/build_weak_label_relief_coverage_policy.py scripts/train_weak_label_rgb_relief_baseline.py scripts/evaluate_weak_label_priority_blend.py scripts/build_weak_label_error_review_queue.py scripts/build_weak_label_error_review_figures.py scripts/build_weak_label_error_review_workspace.py scripts/build_weak_label_p0_visual_dossier.py scripts/build_weak_label_p0_decision_seed.py scripts/build_weak_label_p0_boundary_proposals.py scripts/train_weak_label_castro_mamoa_specialist.py scripts/build_o_val_relief_diagnostics.py scripts/export_training_manifest.py scripts/build_web_review_map.py scripts/check_environment.py scripts/check_repo_drift.py scripts/backup_annotation_workspace.py scripts/sync_wiki_exports.py scripts/run_raspberry_agents.py scripts/render_raspberry_systemd_units.py
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
	rm -rf data/processed/castros-trasancos-mvp data/qgis-review data/annotations data/review-queues data/raster-prep data/training data/morphology-bank data/morphology-autoreview-v1 data/weak-label-splits-v1 data/weak-label-error-review-workspace-v1 reports/*.md webmap/index.html
