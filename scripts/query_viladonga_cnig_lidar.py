#!/usr/bin/env python3
"""Query CNIG LiDAR candidates for the Viladonga morphology pilot."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHIP_MANIFEST = PROJECT_ROOT / "data/viladonga-pilot/pnoa_chip_manifest.tsv"
DEFAULT_OUT = PROJECT_ROOT / "data/viladonga-pilot/cnig_lidar_candidates.tsv"
DEFAULT_REPORT = PROJECT_ROOT / "reports/viladonga_cnig_lidar_candidates.md"
GENERATED_AT = "2026-08-01"
ARCHIVOS_SERIE_URL = "https://centrodedescargas.cnig.es/CentroDescargas/archivosSerie"
DETALLE_URL = "https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo"
INIT_DESCARGA_URL = "https://centrodedescargas.cnig.es/CentroDescargas/initDescargaDir"
DESCARGA_URL = "https://centrodedescargas.cnig.es/CentroDescargas/descargaDir"
USER_AGENT = "castros-ia-galicia/0.1 cnig-lidar-viladonga"

SERIES = {
    "LIDA3": {
        "label": "LIDAR - 3a Cobertura (2022-2025)",
        "priority": 1,
        "expected_unit": "1x1 km",
        "source_url": "https://centrodedescargas.cnig.es/CentroDescargas/lidar-tercera-cobertura",
    },
    "LIDA2": {
        "label": "LIDAR - 2a Cobertura (2015-2021)",
        "priority": 2,
        "expected_unit": "2x2 km with 1x1 exceptions",
        "source_url": "https://centrodedescargas.cnig.es/CentroDescargas/lidar-segunda-cobertura",
    },
    "LIDAR": {
        "label": "LIDAR - 1a Cobertura (2008-2015)",
        "priority": 3,
        "expected_unit": "2x2 km",
        "source_url": "https://centrodedescargas.cnig.es/CentroDescargas/lidar-primera-cobertura",
    },
}

FIELDS = [
    "series_code",
    "series_label",
    "series_priority",
    "query_tile_lower_id",
    "query_x_utm29",
    "query_y_utm29",
    "query_lon_wgs84",
    "query_lat_wgs84",
    "query_total_archivos",
    "file_name",
    "sec",
    "detail_url",
    "download_url",
    "product",
    "year",
    "density_or_scale",
    "size_mb",
    "format",
    "download_unit",
    "init_download_status",
    "downloaded_path",
    "status",
    "notes",
]


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def pilot_bounds(chip_manifest: Path) -> tuple[float, float, float, float]:
    rows = read_tsv(chip_manifest)
    if not rows:
        raise SystemExit(f"Empty chip manifest: {chip_manifest}")
    minx = min(float(row["bbox_raster_crs"].split(",")[0]) for row in rows)
    miny = min(float(row["bbox_raster_crs"].split(",")[1]) for row in rows)
    maxx = max(float(row["bbox_raster_crs"].split(",")[2]) for row in rows)
    maxy = max(float(row["bbox_raster_crs"].split(",")[3]) for row in rows)
    return minx, miny, maxx, maxy


def query_points_for_1km_tiles(bounds: tuple[float, float, float, float]) -> list[dict[str, str]]:
    minx, miny, maxx, maxy = bounds
    points = []
    for xkm in range(int(minx // 1000), int(maxx // 1000) + 1):
        for ykm in range(int(miny // 1000), int(maxy // 1000) + 1):
            x = min(max(xkm * 1000 + 500.0, minx + 1.0), maxx - 1.0)
            y = min(max(ykm * 1000 + 500.0, miny + 1.0), maxy - 1.0)
            lon, lat = utm29_to_lonlat(x, y)
            points.append(
                {
                    "query_tile_lower_id": f"{xkm}-{ykm}",
                    "query_x_utm29": f"{x:.2f}",
                    "query_y_utm29": f"{y:.2f}",
                    "query_lon_wgs84": f"{lon:.8f}",
                    "query_lat_wgs84": f"{lat:.8f}",
                }
            )
    return points


def utm29_to_lonlat(x: float, y: float) -> tuple[float, float]:
    # ETRS89 and WGS84 are close enough here for selecting a CNIG tile by point.
    zone = 29
    a = 6378137.0
    f = 1 / 298.257223563
    e2 = f * (2 - f)
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    k0 = 0.9996
    x0 = x - 500000.0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512
    fp = mu + j1 * math.sin(2 * mu) + j2 * math.sin(4 * mu) + j3 * math.sin(6 * mu) + j4 * math.sin(8 * mu)
    ep2 = e2 / (1 - e2)
    c1 = ep2 * math.cos(fp) ** 2
    t1 = math.tan(fp) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(fp) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(fp) ** 2) ** 1.5
    d = x0 / (n1 * k0)
    lat = fp - (n1 * math.tan(fp) / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / math.cos(fp)
    return math.degrees(lon), math.degrees(lat)


def get_url(url: str, params: dict[str, str] | None = None, *, data: dict[str, str] | None = None, timeout: int = 60) -> bytes:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    encoded_data = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=encoded_data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def query_archivos_serie(series_code: str, lon: str, lat: str) -> tuple[str, list[tuple[str, str]]]:
    coords = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]}}],
    }
    params = {
        "numPagina": "1",
        "codAgr": "MOMDT",
        "codSerie": series_code,
        "coordenadas": json.dumps(coords, separators=(",", ":")),
        "series": "",
        "codComAutonoma": "",
        "codProvincia": "",
        "codIne": "",
        "codTipoArchivo": "",
        "codIdiomaInf": "",
        "todaEspania": "N",
        "todoMundo": "N",
        "idProductor": "",
        "rutaNombre": "",
        "numHoja": "",
        "numHoja25": "",
        "totalArchivos": "",
        "codSubSerie": "",
        "contieneArc": "",
        "keySearch": "",
        "referCatastral": "",
        "orderBy": "",
    }
    # El CNIG devuelve 403 a GET en este endpoint desde el 2026-08-23; los
    # mismos parametros por POST devuelven 200 con los 67 KB de siempre.
    # Medido con curl, mismos params y misma maquina en el mismo instante.
    text = get_url(ARCHIVOS_SERIE_URL, data=params).decode("utf-8", "replace")
    total_match = re.search(r'id="totalArchivos"\s+name="totalArchivos"\s+value="([^"]*)"', text)
    total = total_match.group(1) if total_match else ""
    files = re.findall(
        r'<div class="col-m-8 lineHeight30 displayInlineBlock txtLeftCenterTablas">\s*([^<]+?)\s*</div>.*?'
        r'<a href="\./detalleArchivo\?sec=([0-9]+)"',
        text,
        flags=re.S,
    )
    return total, [(normalise_filename(name), sec) for name, sec in files]


def normalise_filename(name: str) -> str:
    return html.unescape(name).strip().replace(".LAZ", ".laz")


def parse_detail(sec: str) -> dict[str, str]:
    text = get_url(DETALLE_URL, params={"sec": sec}).decode("utf-8", "replace")
    info_match = re.search(r'<div class="col-12 margen10derizq">\s*(.*?)\s*</div>', text, flags=re.S)
    info_html = info_match.group(1) if info_match else text
    cleaned = re.sub(r"<[^>]+>", " ", info_html)
    cleaned = html.unescape(re.sub(r"\s+", " ", cleaned))

    def value_after(label: str, stop_labels: tuple[str, ...]) -> str:
        pattern = re.escape(label) + r"\s*(.*?)\s*(?:" + "|".join(re.escape(stop) for stop in stop_labels) + r")"
        match = re.search(pattern, cleaned, flags=re.I)
        if match:
            return match.group(1).strip()
        tail_match = re.search(re.escape(label) + r"\s*(.*?)\s*$", cleaned, flags=re.I)
        return tail_match.group(1).strip() if tail_match else ""

    filename_match = re.search(r"<h1[^>]*>\s*([^<]+?\.LAZ)\s*</h1>", text, flags=re.I)
    filename = normalise_filename(filename_match.group(1)) if filename_match else ""
    return {
        "product": value_after("Producto:", ("Fichero:",)),
        "file_name": filename or normalise_filename(value_after("Fichero:", ("Fecha:",))),
        "year": value_after("Fecha:", (":", "Tamaño:")),
        "density_or_scale": value_after(f"Fecha: {value_after('Fecha:', (':', 'Tamaño:'))} :", ("Tamaño:",)),
        "size_mb": value_after("Tamaño:", ("Formato:",)).replace("(Mb)", "").strip(),
        "format": value_after("Formato:", ("Sistema de Referencia Geodésico:",)),
        "download_unit": value_after("Unidad de descarga:", ("Licencia", "Contenido auxiliar")),
    }


def init_download(sec: str) -> str:
    try:
        # POST, non GET. O CNIG empezou a devolver 403 en `initDescargaDir`
        # cando se lle pregunta por GET; con POST responde 200 e o JSON
        # normal. E o mesmo cambio que xa fixera falta en
        # `query_archivos_serie`: alli arranxouse e aqui quedou sen tocar,
        # e por iso a cache de Galicia levaba desde o 2026-08-22 marcando
        # bloques como "mar ou fora de cobertura" sen baixar unha tesela.
        payload = get_url(INIT_DESCARGA_URL, data={"secuencial": sec}).decode("utf-8", "replace")
        parsed = json.loads(payload)
    except Exception as exc:
        return f"init_error:{exc}"
    if parsed.get("secuencialDescDir") == sec and parsed.get("muestraLic") == "NO":
        return "ready_no_interactive_license"
    if parsed.get("secuencialDescDir") == sec:
        return f"ready_license_{parsed.get('muestraLic', 'unknown')}"
    return "unexpected_init_response"


def download_file(sec: str, file_name: str, download_dir: Path) -> tuple[str, str]:
    download_dir.mkdir(parents=True, exist_ok=True)
    out_path = download_dir / file_name
    if out_path.exists() and out_path.stat().st_size > 0:
        return str(out_path), "exists"
    curl = shutil.which("curl")
    if not curl:
        return "", "download_error:curl_not_found"
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")
    cmd = [
        curl,
        "-L",
        "-A",
        USER_AGENT,
        "-o",
        str(tmp_path),
        "-X",
        "POST",
        DESCARGA_URL,
        "--data-urlencode",
        f"secDescDirLA={sec}",
    ]
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        return "", f"download_error:curl_exit_{completed.returncode}"
    if tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        return "", "download_error:empty_file"
    tmp_path.replace(out_path)
    return str(out_path), "downloaded"


def build_rows(series_codes: list[str], points: list[dict[str, str]], download_dir: Path | None) -> list[dict[str, str]]:
    rows = []
    seen: set[tuple[str, str, str]] = set()
    for series_code in series_codes:
        series = SERIES[series_code]
        for point in points:
            total, files = query_archivos_serie(series_code, point["query_lon_wgs84"], point["query_lat_wgs84"])
            if not files:
                rows.append(empty_row(series_code, series, point, total, "not_found", "CNIG returned no files for this point."))
                continue
            for file_name, sec in files:
                key = (series_code, sec, point["query_tile_lower_id"])
                if key in seen:
                    continue
                seen.add(key)
                detail = parse_detail(sec)
                file_name = detail.get("file_name") or file_name
                init_status = init_download(sec)
                downloaded_path = ""
                status = "ready_to_download"
                notes = ""
                if download_dir and series_code == "LIDA3":
                    downloaded_path, status = download_file(sec, file_name, download_dir)
                rows.append(
                    {
                        "series_code": series_code,
                        "series_label": series["label"],
                        "series_priority": str(series["priority"]),
                        **point,
                        "query_total_archivos": total,
                        "file_name": file_name,
                        "sec": sec,
                        "detail_url": f"{DETALLE_URL}?sec={sec}",
                        "download_url": DESCARGA_URL,
                        "product": detail.get("product", ""),
                        "year": detail.get("year", ""),
                        "density_or_scale": detail.get("density_or_scale", ""),
                        "size_mb": detail.get("size_mb", ""),
                        "format": detail.get("format", ""),
                        "download_unit": detail.get("download_unit", ""),
                        "init_download_status": init_status,
                        "downloaded_path": downloaded_path,
                        "status": status,
                        "notes": notes,
                    }
                )
    return rows


def empty_row(series_code: str, series: dict[str, object], point: dict[str, str], total: str, status: str, notes: str) -> dict[str, str]:
    return {
        "series_code": series_code,
        "series_label": str(series["label"]),
        "series_priority": str(series["priority"]),
        **point,
        "query_total_archivos": total,
        "file_name": "",
        "sec": "",
        "detail_url": "",
        "download_url": "",
        "product": "",
        "year": "",
        "density_or_scale": "",
        "size_mb": "",
        "format": "",
        "download_unit": "",
        "init_download_status": "",
        "downloaded_path": "",
        "status": status,
        "notes": notes,
    }


def dedupe_preferred(rows: list[dict[str, str]], series_code: str) -> list[dict[str, str]]:
    seen = set()
    preferred = []
    for row in rows:
        if row["series_code"] != series_code or not row["sec"]:
            continue
        key = (row["series_code"], row["sec"])
        if key in seen:
            continue
        seen.add(key)
        preferred.append(row)
    return preferred


def write_report(
    path: Path,
    rows: list[dict[str, str]],
    chip_manifest: Path,
    bounds: tuple[float, float, float, float],
    points: list[dict[str, str]],
    out_path: Path,
) -> None:
    preferred = dedupe_preferred(rows, "LIDA3")
    fallback2 = dedupe_preferred(rows, "LIDA2")
    fallback1 = dedupe_preferred(rows, "LIDAR")
    queried_series = {row["series_code"] for row in rows}
    preferred_ready = len(preferred) == len(points) and all(row["status"] in {"ready_to_download", "downloaded", "exists"} for row in preferred)
    preferred_downloaded = bool(preferred) and all(row["status"] in {"downloaded", "exists"} for row in preferred)
    total_mb = sum(parse_mb(row["size_mb"]) for row in preferred)
    title = "Viladonga CNIG LiDAR downloads" if preferred_downloaded else "Viladonga CNIG LiDAR candidates"
    status = "downloaded_lida3" if preferred_downloaded else ("ready_to_download_lida3" if preferred_ready else "incomplete_lida3")
    lines = [
        f"# {title}",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        f"- Chip manifest: `{rel_to_project(chip_manifest)}`",
        f"- Output TSV: `{rel_to_project(out_path)}`",
        "- Official source: `https://centrodedescargas.cnig.es/CentroDescargas/lidar-tercera-cobertura`",
        "- Product definitions: `https://pnoa.ign.es/pnoa-lidar/productos-a-descarga`",
        f"- Pilot chip bounds EPSG:25829: `{bounds[0]:.2f},{bounds[1]:.2f},{bounds[2]:.2f},{bounds[3]:.2f}`",
        f"- Queried 1 km cells from lower-left IDs: {', '.join(point['query_tile_lower_id'] for point in points)}",
        f"- Preferred status: `{status}`",
        "",
        "## Preferred 3rd coverage LAZ",
        "",
    ]
    if preferred:
        lines.append("| File | Sec | Query lower tile | Year | Density | Size MB | Init status |")
        lines.append("|---|---:|---|---:|---|---:|---|")
        for row in preferred:
            lines.append(
                f"| `{row['file_name']}` | {row['sec']} | `{row['query_tile_lower_id']}` | {row['year']} | {row['density_or_scale']} | {row['size_mb']} | `{row['init_download_status']}` |"
            )
        lines.extend(
            [
                "",
                f"Approximate preferred download size: `{total_mb:.2f} MB`.",
                "",
                "CNIG's 3rd-coverage filenames here use the northern kilometre edge for the Y component: for example, the query point inside lower cell `630-4779` returns `630-4780`.",
            ]
        )
    else:
        lines.append("- No preferred LIDA3 files found.")
    lines.extend(["", "## Fallback coverages", ""])
    if "LIDA2" in queried_series:
        lines.append(f"- 2nd coverage unique files found: {len(fallback2)}.")
        for row in fallback2:
            lines.append(f"  - `{row['file_name']}` sec `{row['sec']}` ({row['density_or_scale']}, {row['size_mb']} MB)")
    else:
        lines.append("- 2nd coverage: not queried in this run.")
    if "LIDAR" in queried_series:
        lines.append(f"- 1st coverage unique files found: {len(fallback1)}.")
        for row in fallback1:
            lines.append(f"  - `{row['file_name']}` sec `{row['sec']}` ({row['density_or_scale']}, {row['size_mb']} MB)")
    else:
        lines.append("- 1st coverage: not queried in this run.")
    lines.extend(
        [
            "",
            "## Download command",
            "",
            "The script does not download heavy LAZ by default. To download only the preferred 3rd-coverage files into the ignored external-data area:",
            "",
            "```bash",
            "python3 scripts/query_viladonga_cnig_lidar.py --coverage LIDA3 --download-dir data/external/viladonga/cnig-lidar-3a",
            "```",
            "",
            "Each download is a POST to `https://centrodedescargas.cnig.es/CentroDescargas/descargaDir` with `secDescDirLA=<sec>` after `initDescargaDir` confirms no interactive licence step.",
            "",
            "## Interpretation",
            "",
            "This resolves the previous LAZ blocker for Viladonga. If the preferred files are already downloaded, the next morphology step is to rebuild the DEM/relief derivatives from point cloud data and rerun the relief/radial baselines against the MDT5 WCS results.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_mb(value: str) -> float:
    try:
        return float(value.replace(",", ".").strip())
    except ValueError:
        return 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query CNIG LiDAR candidates for the Viladonga pilot.")
    parser.add_argument("--chip-manifest", type=Path, default=DEFAULT_CHIP_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--coverage", action="append", choices=sorted(SERIES), help="CNIG series code to query. Repeatable.")
    parser.add_argument("--download-dir", type=Path, help="Download preferred LIDA3 LAZ files into this directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chip_manifest = args.chip_manifest if args.chip_manifest.is_absolute() else PROJECT_ROOT / args.chip_manifest
    out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    report_path = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    download_dir = None
    if args.download_dir:
        download_dir = args.download_dir if args.download_dir.is_absolute() else PROJECT_ROOT / args.download_dir
    series_codes = args.coverage or ["LIDA3", "LIDA2", "LIDAR"]
    bounds = pilot_bounds(chip_manifest)
    points = query_points_for_1km_tiles(bounds)
    rows = build_rows(series_codes, points, download_dir)
    write_tsv(out_path, rows)
    write_report(report_path, rows, chip_manifest, bounds, points, out_path)
    preferred = dedupe_preferred(rows, "LIDA3")
    print(f"queried_points={len(points)}")
    print(f"rows={len(rows)}")
    print(f"lida3_unique_files={len(preferred)}")
    print(f"out={out_path}")
    print(f"report={report_path}")
    if any(row["status"].startswith("download_error") for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
