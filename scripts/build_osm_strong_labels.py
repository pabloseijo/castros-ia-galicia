#!/usr/bin/env python3
"""Build a strong-label bank of castro and mámoa polygons from OpenStreetMap.

The project has been blocked on `accepted_positive_polygons=0` since the
start: everything so far is a chip ranker trained on points and buffers,
which is why it reports "this cell looks castro-ish" instead of locating
anything. Orengo-style detection needs geometry.

OSM contributors have already drawn much of it. Within Galicia there are
~292 `fortification_type=hill_fort`, ~261 `historic:civilization=castro_culture`
and ~375 `archaeological_site=tumulus` closed ways — real outlines for both
the target class and the dominant false positive.

This is not a substitute for archaeological verification. OSM geometry is
volunteered, of uneven precision, and traced from imagery rather than
surveyed. It is a starting bank to review, not ground truth to trust.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = PROJECT_ROOT / "data/osm-strong-labels-v1/osm_raw.json"
DEFAULT_MASTER = PROJECT_ROOT / "data/weak-label-splits-v1/weak_label_master.tsv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data/osm-strong-labels-v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/osm_strong_labels_v1.md"

CASTRO_NAME = re.compile(r"\bcastro|\bcroa\b|cividade|castrom|castrel", re.I)
MOUND_NAME = re.compile(r"m[áa]moa|medorra|arca\b|anta\b|dolmen|t[uú]mulo", re.I)

FIELDS = [
    "osm_id",
    "osm_type",
    "label_class",
    "site_class",
    "name",
    "confidence",
    "evidence",
    "archaeological_site",
    "civilization",
    "fortification_type",
    "wikidata",
    "centroid_lon",
    "centroid_lat",
    "area_m2",
    "perimeter_m",
    "equivalent_radius_m",
    "circularity",
    "vertices",
    "matched_catalogue_id",
    "matched_catalogue_name",
    "matched_distance_m",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=fields, dialect="excel-tab", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi, d_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def ring_metrics(geometry: list[dict]) -> dict[str, float] | None:
    """Planar area, perimeter and circularity from a lon/lat ring."""
    if len(geometry) < 4:
        return None
    lats = [p["lat"] for p in geometry]
    lons = [p["lon"] for p in geometry]
    lat0 = statistics.fmean(lats)
    mx = 111320.0 * math.cos(math.radians(lat0))
    my = 111320.0
    pts = [((p["lon"] - lons[0]) * mx, (p["lat"] - lats[0]) * my) for p in geometry]
    if pts[0] != pts[-1]:
        pts.append(pts[0])

    area = 0.0
    perimeter = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        area += x1 * y2 - x2 * y1
        perimeter += math.hypot(x2 - x1, y2 - y1)
    area = abs(area) / 2.0
    if area <= 0 or perimeter <= 0:
        return None
    return {
        "area_m2": area,
        "perimeter_m": perimeter,
        "equivalent_radius_m": math.sqrt(area / math.pi),
        # 1.0 is a perfect circle; hillforts sit lower than mounds.
        "circularity": 4.0 * math.pi * area / (perimeter ** 2),
        "centroid_lon": statistics.fmean(lons),
        "centroid_lat": statistics.fmean(lats),
        "vertices": float(len(geometry)),
    }


def classify(tags: dict[str, str]) -> tuple[str, str, str]:
    """Return (site_class, confidence, evidence)."""
    site = (tags.get("archaeological_site") or "").lower()
    civ = (tags.get("historic:civilization") or "").lower()
    fort = (tags.get("fortification_type") or "").lower()
    name = tags.get("name") or ""

    if fort in {"hill_fort", "ringfort"}:
        return "castro", "high", f"fortification_type={fort}"
    if civ == "castro_culture":
        return "castro", "high", "civilization=castro_culture"
    if site == "tumulus":
        return "mound", "high", "archaeological_site=tumulus"
    if site == "megalith":
        return "mound", "high", "archaeological_site=megalith"
    if site == "fortification" and civ in {"celtic", "prehistoric", ""}:
        return "castro", "medium", f"site=fortification,civ={civ or 'none'}"
    if site == "settlement" and civ in {"castro_culture", "celtic", "prehistoric"}:
        return "castro", "medium", f"site=settlement,civ={civ}"
    if MOUND_NAME.search(name):
        return "mound", "low", "name_only"
    if CASTRO_NAME.search(name) and site not in {"petroglyph", "necropolis", "roman_villa"}:
        return "castro", "low", "name_only"
    return "other", "none", f"site={site or 'none'}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--match-radius-m", type=float, default=250.0)
    parser.add_argument("--min-confidence", default="medium", choices=["low", "medium", "high"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for attr in ("raw", "master", "out_dir", "report"):
        value = getattr(args, attr)
        setattr(args, attr, value if value.is_absolute() else PROJECT_ROOT / value)

    elements = json.loads(args.raw.read_text(encoding="utf-8"))["elements"]

    catalogue = []
    for row in read_tsv(args.master):
        try:
            catalogue.append(
                (float(row["longitude"]), float(row["latitude"]), row.get("sample_id", ""),
                 row.get("name", ""), row.get("label_class", ""))
            )
        except (KeyError, ValueError):
            continue

    rows: list[dict[str, str]] = []
    skipped = Counter()
    for element in elements:
        tags = element.get("tags", {})
        geometry = element.get("geometry")
        if not geometry:
            skipped["no_geometry"] += 1
            continue
        metrics = ring_metrics(geometry)
        if not metrics:
            skipped["degenerate_ring"] += 1
            continue
        site_class, confidence, evidence = classify(tags)
        if site_class == "other":
            skipped["not_castro_or_mound"] += 1
            continue

        lon, lat = metrics["centroid_lon"], metrics["centroid_lat"]
        best = None
        best_distance = float("inf")
        for c_lon, c_lat, c_id, c_name, _c_class in catalogue:
            if abs(c_lon - lon) > 0.01 or abs(c_lat - lat) > 0.01:
                continue
            distance = haversine_m(lon, lat, c_lon, c_lat)
            if distance < best_distance:
                best_distance, best = distance, (c_id, c_name)

        matched = best is not None and best_distance <= args.match_radius_m
        rows.append(
            {
                "osm_id": str(element.get("id", "")),
                "osm_type": element.get("type", ""),
                "label_class": "1" if site_class == "castro" else "0",
                "site_class": site_class,
                "name": tags.get("name", ""),
                "confidence": confidence,
                "evidence": evidence,
                "archaeological_site": tags.get("archaeological_site", ""),
                "civilization": tags.get("historic:civilization", ""),
                "fortification_type": tags.get("fortification_type", ""),
                "wikidata": tags.get("wikidata", ""),
                "centroid_lon": f"{lon:.8f}",
                "centroid_lat": f"{lat:.8f}",
                "area_m2": f"{metrics['area_m2']:.1f}",
                "perimeter_m": f"{metrics['perimeter_m']:.1f}",
                "equivalent_radius_m": f"{metrics['equivalent_radius_m']:.1f}",
                "circularity": f"{metrics['circularity']:.4f}",
                "vertices": str(int(metrics["vertices"])),
                "matched_catalogue_id": best[0] if matched else "",
                "matched_catalogue_name": best[1] if matched else "",
                "matched_distance_m": f"{best_distance:.0f}" if matched else "",
                "_geometry": geometry,
            }
        )

    order = {"high": 3, "medium": 2, "low": 1}
    keep = [r for r in rows if order[r["confidence"]] >= order[args.min_confidence]]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_tsv(args.out_dir / "osm_strong_labels.tsv", keep, FIELDS)

    features = []
    for row in keep:
        coords = [[p["lon"], p["lat"]] for p in row["_geometry"]]
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {k: row[k] for k in FIELDS},
            }
        )
    geojson_path = args.out_dir / "osm_strong_labels.geojson"
    geojson_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )

    castros = [r for r in keep if r["site_class"] == "castro"]
    mounds = [r for r in keep if r["site_class"] == "mound"]
    matched = [r for r in keep if r["matched_catalogue_id"]]

    def radius_stats(items):
        values = sorted(float(r["equivalent_radius_m"]) for r in items)
        if not values:
            return (0, 0, 0)
        return (
            values[len(values) // 10],
            statistics.median(values),
            values[(9 * len(values)) // 10],
        )

    c_p10, c_med, c_p90 = radius_stats(castros)
    m_p10, m_med, m_p90 = radius_stats(mounds)

    lines = [
        "# Strong labels from OpenStreetMap",
        "",
        "## Why this exists",
        "",
        "`accepted_positive_polygons=0` has been the project's top blocker since",
        "the beginning. Without geometry there is no detector, only a chip ranker",
        "that says \"this 512 m cell looks castro-ish\" and cannot locate anything.",
        "",
        "OSM contributors have already traced much of Galicia's archaeology.",
        "",
        "## Bank",
        "",
        "| class | polygons |",
        "|---|---:|",
        f"| castro | `{len(castros)}` |",
        f"| mound (mámoa/megalith) | `{len(mounds)}` |",
        f"| **total** | **`{len(keep)}`** |",
        "",
        f"- matched to an existing catalogue point (within `{args.match_radius_m:.0f} m`): `{len(matched)}`",
        f"- confidence filter applied: `{args.min_confidence}` and above",
        "",
        "## Size, measured at last",
        "",
        "The project could never test whether size separates castros from mámoas,",
        "because it had no geometry. Now it can:",
        "",
        "| class | p10 radius | median radius | p90 radius |",
        "|---|---:|---:|---:|",
        f"| castro | `{c_p10:.0f} m` | **`{c_med:.0f} m`** | `{c_p90:.0f} m` |",
        f"| mound | `{m_p10:.0f} m` | **`{m_med:.0f} m`** | `{m_p90:.0f} m` |",
        "",
    ]
    if c_med > 0 and m_med > 0:
        lines.append(
            f"Castros are about `{c_med / m_med:.1f}x` the radius of mounds. That is the "
            "physical difference the 5 m ring features were too coarse to exploit."
        )
    lines += [
        "",
        "## What this is not",
        "",
        "- **Not ground truth.** OSM geometry is volunteered, traced from imagery,",
        "  and of uneven precision. Some outlines are the enclosure, others the hill.",
        "- **Not verified archaeology.** A `hill_fort` tag is a contributor's opinion.",
        "- **Not a licence shortcut.** OSM is ODbL: derived data carries obligations,",
        "  which matters if any of this is ever published.",
        "",
        "It is a review bank that turns a blocked task into a checking task, which",
        "is a far cheaper kind of work than drawing several hundred polygons by hand.",
        "",
        "## Next",
        "",
        "1. Open the GeoPackage in QGIS and check a sample against PNOA and hillshade.",
        "2. Promote the ones that survive into `data/annotations/`.",
        "3. With geometry on both classes, an object detector becomes possible.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"castros={len(castros)} mounds={len(mounds)} total={len(keep)} matched={len(matched)}")
    print(f"castro radius median={c_med:.0f} m | mound radius median={m_med:.0f} m")
    print(f"tsv={args.out_dir / 'osm_strong_labels.tsv'}")
    print(f"geojson={geojson_path}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
