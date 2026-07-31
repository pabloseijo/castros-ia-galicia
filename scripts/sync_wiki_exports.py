#!/usr/bin/env python3
"""Copy lightweight generated artifacts to the surrounding Mimir wiki folder."""

from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WIKI_PROJECT_DIR = PROJECT_ROOT.parent
DEST_ROOT = WIKI_PROJECT_DIR / "datos"

EXPORTS = [
    (PROJECT_ROOT / "data/processed/castros-trasancos-mvp", DEST_ROOT / "castros-trasancos-mvp"),
    (PROJECT_ROOT / "data/qgis-review", DEST_ROOT / "castros-trasancos-qgis-review"),
]


def copy_tree_contents(source: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        shutil.copy2(path, destination / path.name)
        copied += 1
    return copied


def main() -> None:
    total = 0
    for source, destination in EXPORTS:
        if not source.exists():
            raise SystemExit(f"Missing generated export directory: {source}")
        count = copy_tree_contents(source, destination)
        total += count
        print(f"synced {count} files: {destination}")
    print(f"synced_total={total}")


if __name__ == "__main__":
    main()
