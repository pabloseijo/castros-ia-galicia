#!/usr/bin/env python3
"""Back up the editable QGIS annotation workspace."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANNOTATION_GPKG = PROJECT_ROOT / "data/annotations/castros_annotations.gpkg"
BACKUP_DIR = PROJECT_ROOT / "data/annotation-backups"
REPORT_PATH = PROJECT_ROOT / "reports/annotation_backup_status.md"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def verify_gpkg(path: Path) -> dict[str, int]:
    if not path.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    counts = {}
    for table in ["labels_reviewed", "negative_areas_reviewed", "geocoded_sites_reviewed", "site_review_decisions", "negative_review_decisions"]:
        cur.execute(f"select count(*) from {table}")
        counts[table] = int(cur.fetchone()[0])
    conn.close()
    return counts


def copy_sidecar(path: Path, backup_path: Path) -> list[Path]:
    copied = [backup_path]
    shutil.copy2(path, backup_path)
    for suffix in ["-wal", "-shm"]:
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            sidecar_backup = Path(str(backup_path) + suffix)
            shutil.copy2(sidecar, sidecar_backup)
            copied.append(sidecar_backup)
    return copied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Back up data/annotations/castros_annotations.gpkg.")
    parser.add_argument("--backup-dir", type=Path, default=BACKUP_DIR)
    parser.add_argument("--verify-only", action="store_true", help="Verify the workspace and write a report without copying it.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    counts = verify_gpkg(ANNOTATION_GPKG)
    copied: list[Path] = []
    if not args.verify_only:
        args.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = args.backup_dir / f"castros_annotations_{utc_stamp()}.gpkg"
        copied = copy_sidecar(ANNOTATION_GPKG, backup_path)

    lines = [
        "# Annotation backup status",
        "",
        f"Generated: {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}",
        "",
        f"- Workspace: `{ANNOTATION_GPKG.relative_to(PROJECT_ROOT)}`",
        f"- Mode: {'verify_only' if args.verify_only else 'backup'}",
        "",
        "## Counts",
        "",
    ]
    lines.extend(f"- {table}: {count}" for table, count in counts.items())
    if copied:
        lines.extend(["", "## Copied files", ""])
        lines.extend(f"- `{path.relative_to(PROJECT_ROOT)}`" for path in copied)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"annotation_workspace_ok backups={len(copied)}")
    for table, count in counts.items():
        print(f"{table}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
