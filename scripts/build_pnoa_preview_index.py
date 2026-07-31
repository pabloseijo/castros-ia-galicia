#!/usr/bin/env python3
"""Build a review-only PNOA WMS preview index for candidate raster windows.

The script does not download imagery by default. It only writes deterministic
GetMap URLs that a reviewer can open later.
"""

from __future__ import annotations

import argparse
import csv
import html
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data/raster-prep/candidate_raster_tiles.tsv"
DEFAULT_OUT_TSV = PROJECT_ROOT / "data/raster-prep/pnoa_preview_urls.tsv"
DEFAULT_OUT_HTML = PROJECT_ROOT / "webmap/pnoa_preview_index.html"
DEFAULT_REPORT = PROJECT_ROOT / "reports/pnoa_preview_index.md"
DEFAULT_WMS_BASE = "https://www.ign.es/wms-inspire/pnoa-ma"
DEFAULT_LAYER = "OI.OrthoimageCoverage"
GENERATED_AT = "2026-07-31"
USER_AGENT = "castros-ia-galicia/0.1 research-preview-index"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def build_wms_url(row: dict[str, str], base_url: str, layer: str, width: int, height: int) -> str:
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": row["bbox_wgs84"],
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "TRANSPARENT": "false",
    }
    return f"{base_url}?{urlencode(params)}"


def build_rows(rows: list[dict[str, str]], base_url: str, layer: str, width: int, height: int) -> list[dict[str, str]]:
    out_rows = []
    for row in rows:
        out_rows.append(
            {
                "tile_id": row["tile_id"],
                "site_id": row["site_id"],
                "primary_name": row["primary_name"],
                "municipality": row["municipality"],
                "split": row["split"],
                "dataset_use": row["dataset_use"],
                "center_lon_wgs84": row["center_lon_wgs84"],
                "center_lat_wgs84": row["center_lat_wgs84"],
                "bbox_wgs84": row["bbox_wgs84"],
                "width_px": str(width),
                "height_px": str(height),
                "wms_layer": layer,
                "preview_url": build_wms_url(row, base_url, layer, width, height),
            }
        )
    return out_rows


def smoke_test(urls: list[str], limit: int) -> list[dict[str, Any]]:
    results = []
    for url in urls[:limit]:
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=20) as response:
                first_bytes = response.read(16)
                content_type = response.headers.get("content-type", "")
                ok = response.status == 200 and first_bytes.startswith(b"\x89PNG")
                results.append(
                    {
                        "status": "ok" if ok else "unexpected_response",
                        "http_status": response.status,
                        "content_type": content_type,
                    }
                )
        except Exception as exc:  # pragma: no cover - depends on network state
            results.append({"status": "failed", "error": str(exc)})
    return results


def write_html(path: Path, rows: list[dict[str, str]], generated_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body_rows = []
    for row in rows:
        url = html.escape(row["preview_url"], quote=True)
        name = html.escape(row["primary_name"])
        municipality = html.escape(row["municipality"])
        tile_id = html.escape(row["tile_id"])
        split = html.escape(row["split"])
        body_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td>{tile_id}</td>",
                    f"<td>{name}</td>",
                    f"<td>{municipality}</td>",
                    f"<td>{split}</td>",
                    f'<td><a href="{url}" target="_blank" rel="noopener">PNOA</a></td>',
                    f'<td><img loading="lazy" src="{url}" alt="PNOA preview for {name}"></td>',
                    "</tr>",
                ]
            )
        )
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PNOA preview index</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f6f3;
      color: #18201b;
    }}
    body {{
      margin: 0;
      padding: 24px;
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.2;
    }}
    p {{
      max-width: 860px;
      line-height: 1.5;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid #d7ddd3;
    }}
    th,
    td {{
      padding: 10px;
      border-bottom: 1px solid #d7ddd3;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #e9eee4;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    img {{
      width: 160px;
      height: 160px;
      object-fit: cover;
      border: 1px solid #cfd7c9;
      background: #eef1ea;
    }}
    a {{
      color: #0b5c7a;
    }}
  </style>
</head>
<body>
<main>
  <h1>PNOA preview index</h1>
  <p>Generated {html.escape(generated_at)}. Review-only links from the official IGN PNOA WMS; these previews do not accept labels, download source rasters, or create training data.</p>
  <table>
    <thead>
      <tr>
        <th>Tile</th>
        <th>Site</th>
        <th>Municipality</th>
        <th>Split</th>
        <th>Link</th>
        <th>Preview</th>
      </tr>
    </thead>
    <tbody>
      {"".join(body_rows)}
    </tbody>
  </table>
</main>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def write_report(
    path: Path,
    rows: list[dict[str, str]],
    smoke_results: list[dict[str, Any]],
    generated_at: str,
    wms_base: str,
    layer: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_split: dict[str, int] = {}
    by_municipality: dict[str, int] = {}
    for row in rows:
        by_split[row["split"]] = by_split.get(row["split"], 0) + 1
        by_municipality[row["municipality"]] = by_municipality.get(row["municipality"], 0) + 1

    lines = [
        "# PNOA preview index",
        "",
        f"Generated: {generated_at}",
        "",
        f"- Preview rows: {len(rows)}",
        f"- WMS endpoint: {wms_base}",
        f"- WMS layer: {layer}",
        "- Mode: URL index only; no imagery downloaded or persisted by this job.",
        "- Archaeological rule: a preview URL is not evidence, a label, or training acceptance.",
        "",
        "## By split",
        "",
    ]
    for split, count in sorted(by_split.items()):
        lines.append(f"- {split}: {count}")
    lines.extend(["", "## By municipality", ""])
    for municipality, count in sorted(by_municipality.items()):
        lines.append(f"- {municipality}: {count}")
    lines.extend(["", "## Smoke test", ""])
    if smoke_results:
        for idx, result in enumerate(smoke_results, start=1):
            detail = ", ".join(f"{key}={value}" for key, value in result.items())
            lines.append(f"- URL {idx}: {detail}")
    else:
        lines.append("- Not run. Use `--smoke-test 1` to validate a sample GetMap request.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PNOA WMS preview URL index.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-tsv", type=Path, default=DEFAULT_OUT_TSV)
    parser.add_argument("--out-html", type=Path, default=DEFAULT_OUT_HTML)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--wms-base", default=DEFAULT_WMS_BASE)
    parser.add_argument("--layer", default=DEFAULT_LAYER)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--smoke-test", type=int, default=0, help="Fetch the first N preview URLs and validate PNG headers.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_tsv(args.input)
    out_rows = build_rows(rows, args.wms_base, args.layer, args.width, args.height)
    fields = [
        "tile_id",
        "site_id",
        "primary_name",
        "municipality",
        "split",
        "dataset_use",
        "center_lon_wgs84",
        "center_lat_wgs84",
        "bbox_wgs84",
        "width_px",
        "height_px",
        "wms_layer",
        "preview_url",
    ]
    generated_at = GENERATED_AT
    smoke_results = smoke_test([row["preview_url"] for row in out_rows], args.smoke_test) if args.smoke_test > 0 else []
    write_tsv(args.out_tsv, out_rows, fields)
    write_html(args.out_html, out_rows, generated_at)
    write_report(args.report, out_rows, smoke_results, generated_at, args.wms_base, args.layer)
    print(f"pnoa_preview_urls={len(out_rows)}")
    return 1 if any(result.get("status") != "ok" for result in smoke_results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
