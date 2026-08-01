#!/usr/bin/env python3
"""Score visual morphology signals in the autonomous castro control set.

The output is a verifier, not a final archaeological label. It checks whether
the already-downloaded orthophoto thumbnails contain usable central/ring-like
image signal around the provisional catalogue-point geometry.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTOREVIEW_DIR = PROJECT_ROOT / "data/morphology-autoreview-v1"
DEFAULT_MANIFEST = DEFAULT_AUTOREVIEW_DIR / "orthophoto_thumbnail_manifest.tsv"
DEFAULT_DECISIONS = DEFAULT_AUTOREVIEW_DIR / "autoreview_decisions.tsv"
DEFAULT_POINTS = DEFAULT_AUTOREVIEW_DIR / "control_set_v1_points.geojson"
DEFAULT_OUT = DEFAULT_AUTOREVIEW_DIR / "visual_signal_scores.tsv"
DEFAULT_POINTS_OUT = DEFAULT_AUTOREVIEW_DIR / "control_set_v1_visual_scores.geojson"
DEFAULT_REPORT = PROJECT_ROOT / "reports/morphology_autoreview_visual_signals.md"
GENERATED_AT = "2026-08-01"

TILE_SIDE_M = 512.0
SECTOR_COUNT = 36

FIELDS = [
    "thumbnail_id",
    "control_set_id",
    "bank_id",
    "review_role",
    "country",
    "name",
    "morphology_proxy",
    "negative_type",
    "proposed_radius_m",
    "thumbnail_status",
    "image_path",
    "image_width_px",
    "image_height_px",
    "gray_mean",
    "gray_std",
    "gray_entropy",
    "black_fraction",
    "white_fraction",
    "edge_global_mean",
    "edge_inner_mean",
    "edge_annulus_mean",
    "edge_outer_mean",
    "edge_annulus_to_outer_ratio",
    "edge_annulus_to_inner_ratio",
    "texture_annulus_std",
    "texture_outer_std",
    "texture_annulus_to_outer_ratio",
    "luminance_inner_mean",
    "luminance_outer_mean",
    "luminance_delta_inner_outer",
    "ring_sector_coverage",
    "ring_sector_balance",
    "radial_peak_rank",
    "radial_peak_count",
    "ring_signal_score",
    "ring_signal_tier",
    "metric_eval_use",
    "autonomous_visual_decision",
    "training_use",
    "status",
    "error",
]


def require_runtime() -> None:
    missing = []
    for module in ("numpy", "PIL"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    if missing:
        raise SystemExit(
            "Missing Python modules: "
            + ", ".join(missing)
            + ". Run this through .venv-geo or install the geo/image stack first."
        )


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def rel_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def parse_float(raw_value: str, fallback: float = 0.0) -> float:
    try:
        return float(str(raw_value).replace(",", "."))
    except (TypeError, ValueError):
        return fallback


def load_gray(path: Path):
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype="float32")
    return (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]) / 255.0


def sobel_edges(gray):
    import numpy as np

    padded = np.pad(gray, 1, mode="edge")
    gx = (
        -padded[:-2, :-2]
        + padded[:-2, 2:]
        - 2.0 * padded[1:-1, :-2]
        + 2.0 * padded[1:-1, 2:]
        - padded[2:, :-2]
        + padded[2:, 2:]
    )
    gy = (
        padded[:-2, :-2]
        + 2.0 * padded[:-2, 1:-1]
        + padded[:-2, 2:]
        - padded[2:, :-2]
        - 2.0 * padded[2:, 1:-1]
        - padded[2:, 2:]
    )
    return np.hypot(gx, gy)


def gray_entropy(gray) -> float:
    import numpy as np

    hist, _ = np.histogram(gray, bins=64, range=(0.0, 1.0))
    total = hist.sum()
    if not total:
        return 0.0
    probs = hist[hist > 0] / total
    return float(-(probs * np.log2(probs)).sum())


def mask_mean(values) -> float:
    return float(values.mean()) if values.size else 0.0


def mask_std(values) -> float:
    return float(values.std()) if values.size else 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def norm(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return clamp((value - low) / (high - low), 0.0, 1.0)


def build_masks(shape: tuple[int, int], radius_m: float):
    import numpy as np

    height, width = shape
    yy, xx = np.indices((height, width))
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    distance = np.hypot(xx - center_x, yy - center_y)
    max_radius = min(width, height) * 0.47
    radius_px = clamp(radius_m * min(width, height) / TILE_SIDE_M, 14.0, max_radius)
    annulus_half_width = clamp(radius_px * 0.16, 7.0, 22.0)

    inner = distance <= radius_px * 0.62
    annulus = (distance >= radius_px - annulus_half_width) & (distance <= radius_px + annulus_half_width)
    outer_start = radius_px + annulus_half_width * 2.0
    outer_end = min(max_radius, max(outer_start + annulus_half_width * 3.0, radius_px * 1.95))
    outer = (distance >= outer_start) & (distance <= outer_end)
    if not outer.any():
        outer = distance >= min(max(radius_px * 1.3, 48.0), max_radius * 0.8)

    angles = (np.arctan2(yy - center_y, xx - center_x) + 2.0 * math.pi) % (2.0 * math.pi)
    sector_ids = np.floor(angles / (2.0 * math.pi / SECTOR_COUNT)).astype("int16")
    return radius_px, inner, annulus, outer, sector_ids


def ring_sector_metrics(edges, annulus, outer, sector_ids) -> tuple[float, float]:
    import numpy as np

    if not annulus.any():
        return 0.0, 0.0
    outer_values = edges[outer] if outer.any() else edges.ravel()
    threshold = float(np.percentile(outer_values, 65)) if outer_values.size else 0.0
    sector_means = []
    for sector_id in range(SECTOR_COUNT):
        sector_mask = annulus & (sector_ids == sector_id)
        if sector_mask.sum() < 8:
            continue
        sector_means.append(float(edges[sector_mask].mean()))
    if not sector_means:
        return 0.0, 0.0
    coverage = sum(value > threshold for value in sector_means) / len(sector_means)
    mean_value = statistics.mean(sector_means)
    std_value = statistics.pstdev(sector_means) if len(sector_means) > 1 else 0.0
    balance = mean_value / (mean_value + std_value) if mean_value > 0 else 0.0
    return float(coverage), float(balance)


def radial_peak_rank(edges, radius_px: float) -> tuple[int, int]:
    import numpy as np

    height, width = edges.shape
    yy, xx = np.indices((height, width))
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    distance = np.hypot(xx - center_x, yy - center_y)
    bin_width = max(6.0, radius_px * 0.08)
    max_distance = min(width, height) * 0.48
    means = []
    target_bin = None
    bin_index = 0
    start = max(8.0, radius_px * 0.35)
    value = start
    while value < max_distance:
        band = (distance >= value) & (distance < value + bin_width)
        if band.sum() >= 32:
            means.append((bin_index, float(edges[band].mean())))
            if value <= radius_px < value + bin_width:
                target_bin = bin_index
        value += bin_width
        bin_index += 1
    if target_bin is None or not means:
        return 0, len(means)
    ranked = sorted(means, key=lambda item: item[1], reverse=True)
    for rank, (idx, _mean_value) in enumerate(ranked, start=1):
        if idx == target_bin:
            return rank, len(means)
    return 0, len(means)


def signal_tier(score: float) -> str:
    if score >= 62.0:
        return "strong_centered_ring_signal"
    if score >= 42.0:
        return "moderate_centered_ring_signal"
    return "weak_centered_ring_signal"


def decision_for(row: dict[str, str], tier: str, image_valid: bool) -> tuple[str, str, str]:
    if not image_valid:
        return (
            "exclude_thumbnail_unusable",
            "thumbnail_unusable_refetch_or_manual_followup",
            "exclude_until_independent_label_review",
        )
    role = row.get("review_role", "")
    if role == "positive":
        if tier == "strong_centered_ring_signal":
            decision = "positive_control_visual_signal_strong"
        elif tier == "moderate_centered_ring_signal":
            decision = "positive_control_visual_signal_moderate"
        else:
            decision = "positive_control_visual_signal_weak_followup"
    else:
        if tier == "strong_centered_ring_signal":
            decision = "hard_negative_visual_signal_strong_keep_as_distractor"
        elif tier == "moderate_centered_ring_signal":
            decision = "hard_negative_visual_signal_moderate_keep_as_distractor"
        else:
            decision = "negative_control_visual_signal_weak"
    return (
        "include_visual_signal_metric_eval",
        decision,
        "exclude_until_independent_label_review",
    )


def evaluate_image(row: dict[str, str], decision_row: dict[str, str]) -> dict[str, str]:
    import numpy as np

    out = {field: "" for field in FIELDS}
    image_path = project_path(row.get("thumbnail_path", ""))
    radius_m = parse_float(decision_row.get("proposed_radius_m", ""), 120.0)
    out.update(
        {
            "thumbnail_id": row.get("thumbnail_id", ""),
            "control_set_id": row.get("control_set_id", ""),
            "bank_id": row.get("bank_id", ""),
            "review_role": row.get("review_role", ""),
            "country": row.get("country", ""),
            "name": row.get("name", ""),
            "morphology_proxy": decision_row.get("morphology_proxy", ""),
            "negative_type": decision_row.get("negative_type", ""),
            "proposed_radius_m": f"{radius_m:.1f}",
            "thumbnail_status": row.get("status", ""),
            "image_path": rel_to_project(image_path),
        }
    )
    if row.get("status") != "exists":
        out["status"] = "failed"
        out["error"] = row.get("error", "thumbnail_not_available")
        metric_use, decision, training_use = decision_for(out, "", image_valid=False)
        out["metric_eval_use"] = metric_use
        out["autonomous_visual_decision"] = decision
        out["training_use"] = training_use
        return out
    if not image_path.exists():
        out["status"] = "failed"
        out["error"] = f"missing_thumbnail:{rel_to_project(image_path)}"
        metric_use, decision, training_use = decision_for(out, "", image_valid=False)
        out["metric_eval_use"] = metric_use
        out["autonomous_visual_decision"] = decision
        out["training_use"] = training_use
        return out

    try:
        gray = load_gray(image_path)
        height, width = gray.shape
        out["image_width_px"] = str(width)
        out["image_height_px"] = str(height)
        gray_mean = float(gray.mean())
        gray_std = float(gray.std())
        entropy = gray_entropy(gray)
        black_fraction = float((gray <= 0.02).mean())
        white_fraction = float((gray >= 0.98).mean())
        out.update(
            {
                "gray_mean": f"{gray_mean:.6f}",
                "gray_std": f"{gray_std:.6f}",
                "gray_entropy": f"{entropy:.6f}",
                "black_fraction": f"{black_fraction:.6f}",
                "white_fraction": f"{white_fraction:.6f}",
            }
        )
        if gray_std < 0.01 or entropy < 1.0 or black_fraction + white_fraction > 0.98:
            out["status"] = "failed"
            out["error"] = "thumbnail_blank_or_low_information"
            metric_use, decision, training_use = decision_for(out, "", image_valid=False)
            out["metric_eval_use"] = metric_use
            out["autonomous_visual_decision"] = decision
            out["training_use"] = training_use
            return out

        edges = sobel_edges(gray)
        radius_px, inner, annulus, outer, sector_ids = build_masks(gray.shape, radius_m)
        edge_global = mask_mean(edges.ravel())
        edge_inner = mask_mean(edges[inner])
        edge_annulus = mask_mean(edges[annulus])
        edge_outer = mask_mean(edges[outer])
        texture_annulus = mask_std(gray[annulus])
        texture_outer = mask_std(gray[outer])
        luminance_inner = mask_mean(gray[inner])
        luminance_outer = mask_mean(gray[outer])
        edge_annulus_to_outer = edge_annulus / edge_outer if edge_outer else 0.0
        edge_annulus_to_inner = edge_annulus / edge_inner if edge_inner else 0.0
        texture_annulus_to_outer = texture_annulus / texture_outer if texture_outer else 0.0
        coverage, balance = ring_sector_metrics(edges, annulus, outer, sector_ids)
        peak_rank, peak_count = radial_peak_rank(edges, radius_px)
        peak_component = 0.0
        if peak_rank and peak_count:
            peak_component = 1.0 - ((peak_rank - 1) / max(peak_count - 1, 1))
        contrast = edge_annulus - max(edge_inner, edge_outer)
        score = 100.0 * (
            0.32 * norm(edge_annulus_to_outer, 0.92, 1.42)
            + 0.22 * norm(contrast, 0.0, 0.045)
            + 0.18 * coverage
            + 0.10 * balance
            + 0.10 * norm(texture_annulus_to_outer, 0.92, 1.35)
            + 0.08 * peak_component
        )
        score = clamp(score, 0.0, 100.0)
        tier = signal_tier(score)
        metric_use, decision, training_use = decision_for(out, tier, image_valid=True)
        out.update(
            {
                "edge_global_mean": f"{edge_global:.6f}",
                "edge_inner_mean": f"{edge_inner:.6f}",
                "edge_annulus_mean": f"{edge_annulus:.6f}",
                "edge_outer_mean": f"{edge_outer:.6f}",
                "edge_annulus_to_outer_ratio": f"{edge_annulus_to_outer:.6f}",
                "edge_annulus_to_inner_ratio": f"{edge_annulus_to_inner:.6f}",
                "texture_annulus_std": f"{texture_annulus:.6f}",
                "texture_outer_std": f"{texture_outer:.6f}",
                "texture_annulus_to_outer_ratio": f"{texture_annulus_to_outer:.6f}",
                "luminance_inner_mean": f"{luminance_inner:.6f}",
                "luminance_outer_mean": f"{luminance_outer:.6f}",
                "luminance_delta_inner_outer": f"{(luminance_inner - luminance_outer):.6f}",
                "ring_sector_coverage": f"{coverage:.6f}",
                "ring_sector_balance": f"{balance:.6f}",
                "radial_peak_rank": str(peak_rank),
                "radial_peak_count": str(peak_count),
                "ring_signal_score": f"{score:.2f}",
                "ring_signal_tier": tier,
                "metric_eval_use": metric_use,
                "autonomous_visual_decision": decision,
                "training_use": training_use,
                "status": "ok",
            }
        )
    except Exception as exc:
        out["status"] = "failed"
        out["error"] = str(exc)
        metric_use, decision, training_use = decision_for(out, "", image_valid=False)
        out["metric_eval_use"] = metric_use
        out["autonomous_visual_decision"] = decision
        out["training_use"] = training_use
    return out


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[int(index)]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def merge_points(points_path: Path, scores: list[dict[str, str]], out_path: Path) -> None:
    payload = json.loads(points_path.read_text(encoding="utf-8"))
    by_control_id = {row["control_set_id"]: row for row in scores}
    features = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        control_set_id = props.get("control_set_id", "")
        score_row = by_control_id.get(control_set_id, {})
        merged_props = dict(props)
        for key in (
            "ring_signal_score",
            "ring_signal_tier",
            "metric_eval_use",
            "autonomous_visual_decision",
            "training_use",
            "status",
            "error",
        ):
            if key in score_row:
                merged_props[f"visual_{key}"] = score_row.get(key, "")
        feature = dict(feature)
        feature["properties"] = merged_props
        features.append(feature)
    payload["name"] = "control_set_v1_visual_scores"
    payload["features"] = features
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def counter_by(rows: list[dict[str, str]], *fields: str) -> Counter:
    counter = Counter()
    for row in rows:
        counter[tuple(row.get(field, "") for field in fields)] += 1
    return counter


def format_counter(counter: Counter) -> list[str]:
    lines = []
    for key, count in sorted(counter.items(), key=lambda item: (item[0], item[1])):
        label = "/".join(part or "-" for part in key)
        lines.append(f"- {label}: {count}")
    return lines


def top_rows(rows: list[dict[str, str]], role: str, reverse: bool = True, limit: int = 10) -> list[dict[str, str]]:
    filtered = [row for row in rows if row.get("review_role") == role and row.get("status") == "ok"]
    return sorted(filtered, key=lambda row: parse_float(row.get("ring_signal_score", ""), 0.0), reverse=reverse)[:limit]


def write_report(path: Path, rows: list[dict[str, str]], out_path: Path, points_out: Path) -> None:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    failed_rows = [row for row in rows if row.get("status") != "ok"]
    scores = [parse_float(row.get("ring_signal_score", ""), 0.0) for row in ok_rows]
    pos_scores = [parse_float(row.get("ring_signal_score", ""), 0.0) for row in ok_rows if row.get("review_role") == "positive"]
    neg_scores = [parse_float(row.get("ring_signal_score", ""), 0.0) for row in ok_rows if row.get("review_role") == "negative"]

    lines = [
        "# Morphology Autoreview Visual Signals",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "Second-pass visual verifier over the autonomous control set v1 thumbnails.",
        "It measures whether the official orthophoto chip contains centered edge, texture and radial-ring signal around the provisional catalogue-point radius.",
        "",
        "This is not an archaeological acceptance label and it does not promote any row into training.",
        "The field `training_use` remains `exclude_until_independent_label_review`.",
        "",
        "## Inputs And Outputs",
        "",
        "- Input manifest: `data/morphology-autoreview-v1/orthophoto_thumbnail_manifest.tsv`",
        "- Input decisions: `data/morphology-autoreview-v1/autoreview_decisions.tsv`",
        f"- Output scores: `{rel_to_project(out_path)}`",
        f"- Output points: `{rel_to_project(points_out)}`",
        "- Optional QGIS package: `data/morphology-autoreview-v1/morphology_autoreview_v1_visual_signals.gpkg`",
        "",
        "## Counts",
        "",
        f"- Rows checked: {len(rows)}",
        f"- Valid thumbnails scored: {len(ok_rows)}",
        f"- Failed or unusable thumbnails: {len(failed_rows)}",
        f"- Median score, all valid: {statistics.median(scores):.2f}" if scores else "- Median score, all valid: n/a",
        f"- Median score, positives: {statistics.median(pos_scores):.2f}" if pos_scores else "- Median score, positives: n/a",
        f"- Median score, negatives: {statistics.median(neg_scores):.2f}" if neg_scores else "- Median score, negatives: n/a",
        f"- P25/P75 score, positives: {percentile(pos_scores, 0.25):.2f} / {percentile(pos_scores, 0.75):.2f}" if pos_scores else "- P25/P75 score, positives: n/a",
        f"- P25/P75 score, negatives: {percentile(neg_scores, 0.25):.2f} / {percentile(neg_scores, 0.75):.2f}" if neg_scores else "- P25/P75 score, negatives: n/a",
        "",
        "### By Role And Tier",
        "",
        *format_counter(counter_by(rows, "review_role", "ring_signal_tier")),
        "",
        "### Autonomous Visual Decisions",
        "",
        *format_counter(counter_by(rows, "review_role", "autonomous_visual_decision")),
        "",
        "## Strongest Positive Visual Signals",
        "",
    ]
    for row in top_rows(rows, "positive", reverse=True):
        lines.append(
            f"- {row['control_set_id']} | {row['name']} | score {row['ring_signal_score']} | {row['morphology_proxy']}"
        )
    lines.extend(["", "## Weakest Positive Visual Signals", ""])
    for row in top_rows(rows, "positive", reverse=False):
        lines.append(
            f"- {row['control_set_id']} | {row['name']} | score {row['ring_signal_score']} | {row['morphology_proxy']}"
        )
    lines.extend(["", "## Strongest Hard-Negative Visual Distractors", ""])
    for row in top_rows(rows, "negative", reverse=True):
        lines.append(
            f"- {row['control_set_id']} | {row['name']} | score {row['ring_signal_score']} | {row['negative_type']}"
        )
    if failed_rows:
        lines.extend(["", "## Failed Thumbnails", ""])
        for row in failed_rows:
            lines.append(f"- {row['control_set_id']} | {row['name']} | {row['error']}")
    lines.extend(
        [
            "",
            "## Method",
            "",
            "- Convert the RGB thumbnail to luminance.",
            "- Compute Sobel edge magnitude.",
            "- Estimate the provisional radius in pixels from the 512 m tile window.",
            "- Compare edge and texture in the expected annulus against inner and outer context.",
            "- Add angular coverage and radial-peak rank to avoid treating one isolated edge as a complete enclosure.",
            "",
            "## Caution",
            "",
            "High score means useful morphology signal for metric evaluation, not confirmed castro geometry.",
            "Low score can also happen when vegetation, shadow, urban cover, crop timing or catalogue-point offset hide the structure in RGB orthophoto.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--points", type=Path, default=DEFAULT_POINTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--points-out", type=Path, default=DEFAULT_POINTS_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    require_runtime()
    args = parse_args()
    manifest_rows = read_tsv(args.manifest)
    decision_rows = read_tsv(args.decisions)
    decisions_by_control_id = {
        row.get("control_set_id", ""): row for row in decision_rows if row.get("control_set_id", "")
    }
    scores = [
        evaluate_image(row, decisions_by_control_id.get(row.get("control_set_id", ""), {}))
        for row in manifest_rows
    ]
    write_tsv(args.out, scores)
    merge_points(args.points, scores, args.points_out)
    write_report(args.report, scores, args.out, args.points_out)
    print(f"Wrote {rel_to_project(args.out)} ({len(scores)} rows)")
    print(f"Wrote {rel_to_project(args.points_out)}")
    print(f"Wrote {rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
