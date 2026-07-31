# Raspberry agents

This project can run a small autonomous worker layer on a Raspberry Pi. These agents are deterministic jobs around the existing pipeline; they are not allowed to decide final archaeological labels.

## Current SSH status

From this Codex environment, `ssh raspberry` does not resolve and there is no Raspberry host alias in `~/.ssh/config`. Deployment is therefore prepared but not activated.

Needed later:

```bash
ssh pi@RASPBERRY_IP 'hostname'
```

or a `~/.ssh/config` entry such as:

```sshconfig
Host raspberry
  HostName RASPBERRY_IP
  User pi
```

## Agent contract

Allowed:

- Refresh PBA/Xunta source snapshots.
- Rebuild generated QGIS review layers.
- Refresh reports, webmap, queues and training-readiness checks.
- Record logs and state.

Forbidden:

- Accept archaeological labels automatically.
- Promote PBA or toponymic points into training positives.
- Overwrite human QGIS annotations.
- Train deep-learning models on the Raspberry.
- Bypass anti-bot systems or scrape hostile services aggressively.

## Configured agents

The source of truth is `configs/raspberry_agents.json`.

| Agent | Purpose | Default schedule |
|---|---|---|
| `repo_drift_watchdog` | Fetch origin and report local/remote Git drift without merging. | weekdays 02:50 |
| `annotation_vault` | Back up and verify the editable QGIS annotation workspace. | weekdays 03:05 |
| `env_watchdog` | Check QGIS/GDAL/PDAL/Python module availability. | daily |
| `pba_catalog_monitor` | Refresh PBA/Xunta catalogue snapshot and PBA decision queues. | weekdays 03:20 |
| `qgis_package_refresh` | Rebuild generated QGIS review layers without touching annotations. | weekdays 03:40 |
| `review_outputs_refresh` | Rebuild queues, raster manifest, training readiness and webmap. | weekdays 04:00 |
| `training_readiness_watchdog` | Re-check accepted QGIS labels and metadata. | hourly |
| `full_safe_verify` | Full verification chain; disabled by default. | Sunday 05:00 |

## Local commands

List agents:

```bash
make agent-list
```

Run all enabled agents:

```bash
make agent-run
```

Run one agent:

```bash
make agent-run-one AGENT=pba_catalog_monitor
```

Dry-run:

```bash
python3 scripts/run_raspberry_agents.py --run-enabled --dry-run
```

Agent state and logs:

- `data/agent-state/`
- `data/annotation-backups/`
- `logs/agents/`

These runtime folders are intentionally not versioned.

## Systemd deployment on Raspberry

On the Raspberry, inside the repo:

```bash
python3 scripts/render_raspberry_systemd_units.py --out-dir ops/raspberry/systemd --project-dir "$PWD"
mkdir -p ~/.config/systemd/user
cp ops/raspberry/systemd/*.service ops/raspberry/systemd/*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now castros-ia-repo_drift_watchdog.timer
systemctl --user enable --now castros-ia-annotation_vault.timer
systemctl --user enable --now castros-ia-env_watchdog.timer
systemctl --user enable --now castros-ia-pba_catalog_monitor.timer
systemctl --user enable --now castros-ia-qgis_package_refresh.timer
systemctl --user enable --now castros-ia-review_outputs_refresh.timer
systemctl --user enable --now castros-ia-training_readiness_watchdog.timer
```

Check status:

```bash
systemctl --user list-timers 'castros-ia-*'
python3 scripts/run_raspberry_agents.py --list
```

## Safe annotation rule

`scripts/build_annotation_workspace.py` now refuses to overwrite `data/annotations/castros_annotations.gpkg` unless `--force` is passed. This protects QGIS edits from automated jobs.

Use `make annotations-reset` only after backing up human annotations.

## What remains human

The Raspberry can keep the workshop warm. The archaeological decision still happens in QGIS:

- resolve `remaining_equivalence_candidates`;
- draw accepted polygons in `labels_reviewed`;
- draw accepted negative areas in `negative_areas_reviewed`;
- fill required metadata;
- then run `make training-manifest`.
