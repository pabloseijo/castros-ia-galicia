#!/usr/bin/env python3
"""Check local tooling needed by later raster/model phases.

The current MVP deliberately runs with the Python standard library. Raster
downloads, LiDAR derivatives and model training need heavier optional tools; this
script records what is available without failing the reproducible light pipeline.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"
DEFAULT_REPORT = REPORTS_DIR / "environment_status.md"

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check optional geospatial/model tooling.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--label", default="local", help="Human-readable environment label for the report.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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

    raster_base_blocked = any(name in missing_commands for name in {"gdalinfo", "ogr2ogr", "gdaldem"}) or any(
        name in missing_modules for name in {"rasterio", "geopandas", "shapely", "pyproj"}
    )
    lidar_point_cloud_blocked = "pdal" in missing_commands
    qgis_blocked = "qgis" in missing_commands and "qgis_process" in missing_commands
    model_blocked = any(name in missing_modules for name in {"torch", "ultralytics"})

    lines = [
        "# Environment status",
        "",
        "Generated: 2026-07-31",
        "",
        "## Summary",
        "",
        f"- Environment: {args.label}",
        f"- QGIS available: {'no' if qgis_blocked else 'yes'}",
        f"- Raster/DTM base processing ready: {'no' if raster_base_blocked else 'yes'}",
        f"- LiDAR point-cloud processing ready: {'no' if lidar_point_cloud_blocked else 'yes'}",
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
    if raster_base_blocked:
        lines.append("- Raster/DTM phase needs GDAL plus Python geospatial libraries before cutting image or DEM tiles.")
    if lidar_point_cloud_blocked:
        lines.append("- LiDAR point-cloud phase needs PDAL only if processing original LAZ/COPC point clouds instead of prepared DEM/DTM rasters.")
    if model_blocked:
        lines.append("- YOLO/deep-learning experiments need a model stack such as PyTorch and Ultralytics.")
    if not any([qgis_blocked, raster_base_blocked, lidar_point_cloud_blocked, model_blocked]):
        lines.append("- No local tooling blocker detected; the next blocker is human annotation quality.")

    report_path = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"missing_commands={','.join(missing_commands) if missing_commands else 'none'}")
    print(f"missing_modules={','.join(missing_modules) if missing_modules else 'none'}")
    print(f"qgis_available={'no' if qgis_blocked else 'yes'}")
    print(f"raster_base_processing_ready={'no' if raster_base_blocked else 'yes'}")
    print(f"lidar_point_cloud_processing_ready={'no' if lidar_point_cloud_blocked else 'yes'}")
    print(f"deep_learning_ready={'no' if model_blocked else 'yes'}")
    print(f"report={report_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
