#!/usr/bin/env python3
"""Check local tooling needed by later raster/model phases.

The current MVP deliberately runs with the Python standard library. Raster
downloads, LiDAR derivatives and model training need heavier optional tools; this
script records what is available without failing the reproducible light pipeline.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
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

# The Makefile drives every geospatial target through GEO_PYTHON, so auditing
# only the interpreter running this script reports modules as missing that the
# pipeline actually has. Probe that interpreter too and report both.
GEO_PYTHON_CANDIDATES = [
    PROJECT_ROOT / ".venv-geo/bin/python",
    PROJECT_ROOT / ".venv-geo/bin/python3",
    PROJECT_ROOT / ".venv/bin/python",
]

QGIS_COMMAND_CANDIDATES = {
    "qgis": [
        "/Applications/QGIS.app/Contents/MacOS/QGIS",
        "/Applications/QGIS-LTR.app/Contents/MacOS/QGIS",
    ],
    "qgis_process": [
        "/Applications/QGIS.app/Contents/MacOS/bin/qgis_process",
        "/Applications/QGIS-LTR.app/Contents/MacOS/bin/qgis_process",
    ],
}


def resolve_geo_python() -> Path | None:
    override = os.environ.get("GEO_PYTHON", "").strip()
    candidates = []
    if override:
        candidates.append(Path(override) if Path(override).is_absolute() else PROJECT_ROOT / override)
    candidates.extend(GEO_PYTHON_CANDIDATES)
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    return None


def probe_interpreter(interpreter: Path, modules: list[str]) -> dict[str, str]:
    """Ask another interpreter which of the modules it can import."""
    probe = (
        "import importlib.util, json, sys\n"
        f"mods = {modules!r}\n"
        "out = {}\n"
        "for name in mods:\n"
        "    try:\n"
        "        spec = importlib.util.find_spec(name)\n"
        "    except Exception:\n"
        "        spec = None\n"
        "    if spec is None:\n"
        "        out[name] = ''\n"
        "        continue\n"
        "    try:\n"
        "        mod = __import__(name)\n"
        "        out[name] = str(getattr(mod, '__version__', 'installed'))\n"
        "    except Exception as exc:\n"
        "        out[name] = 'import error: %s' % exc\n"
        "print(json.dumps(out))\n"
    )
    try:
        result = subprocess.run(
            [str(interpreter), "-c", probe],
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        return json.loads(result.stdout.strip() or "{}")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}


def find_command(command: str) -> str:
    path = shutil.which(command)
    if path:
        return path
    for candidate in QGIS_COMMAND_CANDIDATES.get(command, []):
        if Path(candidate).exists() and os.access(candidate, os.X_OK):
            return candidate
    return ""

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
    path = find_command(command)
    if not path:
        return ""
    for args in ([path, "--version"], [path, "-v"]):
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
        path = find_command(command)
        command_rows.append(
            {
                "name": command,
                "purpose": purpose,
                "status": "available" if path else "missing",
                "path": path,
                "version": command_version(command) if path else "",
            }
        )

    geo_python = resolve_geo_python()
    geo_modules = probe_interpreter(geo_python, [name for name, _ in MODULES]) if geo_python else {}

    module_rows = []
    for module, purpose in MODULES:
        available, version = module_status(module)
        geo_version = geo_modules.get(module, "")
        geo_available = bool(geo_version) and not geo_version.startswith("import error")
        module_rows.append(
            {
                "name": module,
                "purpose": purpose,
                "status": "available" if available else "missing",
                "version": version,
                "geo_status": "available" if geo_available else "missing",
                "geo_version": geo_version,
                # The pipeline only needs the module somewhere it actually runs.
                "effective": "available" if (available or geo_available) else "missing",
            }
        )

    missing_commands = [row["name"] for row in command_rows if row["status"] == "missing"]
    missing_modules = [row["name"] for row in module_rows if row["effective"] == "missing"]
    missing_base_modules = [row["name"] for row in module_rows if row["status"] == "missing"]

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
        f"- Base interpreter: `{sys.executable}`",
        f"- Geospatial interpreter (GEO_PYTHON): `{geo_python if geo_python else 'not found'}`",
        f"- QGIS available: {'no' if qgis_blocked else 'yes'}",
        f"- Raster/DTM base processing ready: {'no' if raster_base_blocked else 'yes'}",
        f"- LiDAR point-cloud processing ready: {'no' if lidar_point_cloud_blocked else 'yes'}",
        f"- Deep learning experiment ready: {'no' if model_blocked else 'yes'}",
        "",
        "Readiness is judged against the interpreter each target actually uses.",
        "The Makefile runs every geospatial target through `GEO_PYTHON`, so a",
        "module missing from the base interpreter but present in `.venv-geo` is",
        "not a blocker; it is reported below as a base-only gap.",
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

    lines.extend(
        [
            "",
            "## Python modules",
            "",
            "| Module | Effective | Base | GEO_PYTHON | Purpose | Version |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in module_rows:
        version = (row["geo_version"] or row["version"]).replace("|", "/")
        lines.append(
            f"| `{row['name']}` | {row['effective']} | {row['status']} | {row['geo_status']} | "
            f"{row['purpose']} | {version} |"
        )

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

    print(f"geo_python={geo_python if geo_python else 'not_found'}")
    print(f"missing_commands={','.join(missing_commands) if missing_commands else 'none'}")
    print(f"missing_modules={','.join(missing_modules) if missing_modules else 'none'}")
    print(f"missing_base_only_modules={','.join(missing_base_modules) if missing_base_modules else 'none'}")
    print(f"qgis_available={'no' if qgis_blocked else 'yes'}")
    print(f"raster_base_processing_ready={'no' if raster_base_blocked else 'yes'}")
    print(f"lidar_point_cloud_processing_ready={'no' if lidar_point_cloud_blocked else 'yes'}")
    print(f"deep_learning_ready={'no' if model_blocked else 'yes'}")
    print(f"report={report_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
