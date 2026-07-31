# Raspberry agents

This project can run a small autonomous worker layer on a Raspberry Pi. These agents are deterministic jobs around the existing pipeline; they are not allowed to decide final archaeological labels.

## Current SSH status

The Raspberry connection workflow lives in the local Keltera Brain repo:
`/Users/pabloseijo/Documents/KelteraStudio/Nabia/Keltera-Brain/WORKFLOWS/raspberry-server.md`.

Credentials live in the non-versioned Keltera Brain `.env`. Do not copy them into this repo or into wiki pages.

Use Tailscale first:

```bash
set -a
. /Users/pabloseijo/Documents/KelteraStudio/Nabia/Keltera-Brain/.env
set +a
sshpass -p "$RASPBERRI_SSH_PASSWORD" ssh -o ConnectTimeout=10 "$RASPBERRI_SSH_USER"@"$RASPBERRI_TAILSCALE_HOST" 'hostname'
```

Fallback to the local IP only if Tailscale is offline:

```bash
sshpass -p "$RASPBERRI_SSH_PASSWORD" ssh -o ConnectTimeout=10 "$RASPBERRI_SSH_USER"@"$RASPBERRI_LOCAL_IP" 'hostname'
```

Verified from this Codex environment on 2026-07-31: hostname `raspberri`, user `admin`, port 22 reachable through Tailscale and local network.

Earlier failures came from trying the unresolved alias `raspberry` instead of the configured `raspberri` workflow.

## Agent contract

Allowed:

- Refresh PBA/Xunta source snapshots.
- Rebuild generated QGIS review layers.
- Refresh reports, webmap, queues and training-readiness checks.
- Generate review-only PNOA WMS preview URL indexes.
- Record logs and state.

Forbidden:

- Accept archaeological labels automatically.
- Promote PBA or toponymic points into training positives.
- Overwrite human QGIS annotations.
- Persist or process source rasters before review acceptance.
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
| `pnoa_preview_index` | Rebuild review-only IGN PNOA WMS URLs and an HTML preview page. | weekdays 04:20 |
| `pnoa_chip_export` | Export PNOA chips only from accepted reviewed annotations. | weekdays 04:40 |
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

The PNOA preview index writes:

- `data/raster-prep/pnoa_preview_urls.tsv`
- `webmap/pnoa_preview_index.html`
- `reports/pnoa_preview_index.md`

This is a review aid only. It creates official WMS links and one smoke-test request; it does not download/persist source rasters or create labels.

The PNOA chip export writes:

- `data/training/pnoa_chip_manifest.tsv`
- `reports/pnoa_chip_export.md`
- `data/raster-chips/pnoa/`

This export is gated by accepted human annotations. With zero accepted positives or negatives, it writes an empty manifest and does not download imagery.

The Raspberry environment watchdog writes `reports/environment_status_raspberry.md`, separate from the local Mac report `reports/environment_status.md`.

These runtime folders are intentionally not versioned.

## Systemd deployment on Raspberry

Canonical remote path:

```text
/home/admin/Mimir/wiki/vida/carrera/arqueologia-computacional/castros-ia-galicia
```

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
systemctl --user enable --now castros-ia-pnoa_preview_index.timer
systemctl --user enable --now castros-ia-pnoa_chip_export.timer
systemctl --user enable --now castros-ia-training_readiness_watchdog.timer
```

For timers to keep running after SSH logout, the `admin` user needs linger enabled:

```bash
loginctl show-user admin -p Linger
sudo loginctl enable-linger admin
```

Verified on 2026-07-31: `Linger=yes`.

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
