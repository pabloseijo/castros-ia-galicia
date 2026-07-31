#!/usr/bin/env python3
"""Check local tooling needed by later raster/model phases.

The current MVP deliberately runs with the Python standard library. Raster
downloads, LiDAR derivatives and model training need heavier optional tools; this
script records what is available without failing the reproducible light pipeline.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"

COMMANDS = [
    ("python3", "Python runtime"),
    ("qgis", "QGIS desktop"),
    ("qgis_process", "QGIS processing CLI"),
    ("gdalinfo", "GDAL raster tools"),
    ("ogr2ogr", "GDAL/OGR vector tools"),
    ("gdaldem", "GDAL DEM derivatives"),
    ("pdal", "PDAL point cloud tools"),
]

MODULES = [
    ("numpy", "numeric arrays"),
    ("pandas", "tabular QA"),
    ("geopandas", "vector geodata"),
    ("shapely", "geometry operations"),
    ("pyproj", "CRS transforms"),
    ("fiona", "GeoPackage IO"),
    ("rasterio", "raster windows"),
    ("sklearn", "classical ML baselines"),
    ("torch", "deep learning"),
    ("ultralytics", "YOLO experiments"),
]


def command_version(command: str) -> str:
    path = shutil.which(command)
    if not path:
        return ""
    for args in ([command, "--version"], [command, "-v"]):
        try:
            result = subprocess.run(args, text=True, capture_output=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        output = " ".join((result.stdout or result.stderr).split())
        if output:
            return output[:180]
    return path


def module_status(module: str) -> tuple[bool, str]:
    spec = importlib.util.find_spec(module)
    if spec is None:
        return False, ""
    try:
        imported = __import__(module)
    except Exception as exc:  # pragma: no cover - status report only
        return True, f"import error: {exc}"
    return True, str(getattr(imported, "__version__", "installed"))


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    command_rows = []
    for command, purpose in COMMANDS:
        path = shutil.which(command)
        command_rows.append(
            {
                "name": command,
                "purpose": purpose,
                "status": "available" if path else "missing",
                "path": path or "",
                "version": command_version(command) if path else "",
            }
        )

    module_rows = []
    for module, purpose in MODULES:
        available, version = module_status(module)
        module_rows.append(
            {
                "name": module,
                "purpose": purpose,
                "status": "available" if available else "missing",
                "version": version,
            }
        )

    missing_commands = [row["name"] for row in command_rows if row["status"] == "missing"]
    missing_modules = [row["name"] for row in module_rows if row["status"] == "missing"]

    raster_blocked = any(name in missing_commands for name in {"gdalinfo", "gdaldem", "pdal"}) or any(
        name in missing_modules for name in {"rasterio", "geopandas", "shapely", "pyproj"}
    )
    qgis_blocked = "qgis" in missing_commands and "qgis_process" in missing_commands
    model_blocked = any(name in missing_modules for name in {"torch", "ultralytics"})

    lines = [
        "# Environment status",
        "",
        "Generated: 2026-07-31",
        "",
        "## Summary",
        "",
        f"- QGIS available: {'no' if qgis_blocked else 'yes'}",
        f"- Raster/LiDAR processing ready: {'no' if raster_blocked else 'yes'}",
        f"- Deep learning experiment ready: {'no' if model_blocked else 'yes'}",
        "",
        "The light dataset, QGIS package, reports and web map do not require these optional tools.",
        "",
        "## Commands",
        "",
        "| Tool | Status | Purpose | Path/version |",
        "|---|---|---|---|",
    ]
    for row in command_rows:
        detail = row["version"] or row["path"] or ""
        lines.append(f"| `{row['name']}` | {row['status']} | {row['purpose']} | {detail.replace('|', '/')} |")

    lines.extend(["", "## Python modules", "", "| Module | Status | Purpose | Version |", "|---|---|---|---|"])
    for row in module_rows:
        lines.append(f"| `{row['name']}` | {row['status']} | {row['purpose']} | {row['version'].replace('|', '/')} |")

    lines.extend(["", "## Operational blockers", ""])
    if qgis_blocked:
        lines.append("- Manual visual review still requires opening the GeoPackages in QGIS desktop.")
    if raster_blocked:
        lines.append("- Raster/LiDAR phase needs GDAL/PDAL plus Python geospatial libraries before downloading and cutting tiles.")
    if model_blocked:
        lines.append("- YOLO/deep-learning experiments need a model stack such as PyTorch and Ultralytics.")
    if not any([qgis_blocked, raster_blocked, model_blocked]):
        lines.append("- No local tooling blocker detected; the next blocker is human annotation quality.")

    (REPORTS_DIR / "environment_status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"missing_commands={','.join(missing_commands) if missing_commands else 'none'}")
    print(f"missing_modules={','.join(missing_modules) if missing_modules else 'none'}")
    print(f"qgis_available={'no' if qgis_blocked else 'yes'}")
    print(f"raster_processing_ready={'no' if raster_blocked else 'yes'}")
    print(f"deep_learning_ready={'no' if model_blocked else 'yes'}")


if __name__ == "__main__":
    main()
