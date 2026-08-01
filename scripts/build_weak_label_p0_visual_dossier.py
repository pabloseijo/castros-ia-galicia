#!/usr/bin/env python3
"""Build a visual dossier for the autonomous P0 pretriage queue."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from build_weak_label_error_review_figures import (
    DEFAULT_CHIP_MANIFESTS,
    DEFAULT_RELIEF_MANIFESTS,
    PANEL_SIZE,
    TITLE_HEIGHT,
    by_sample,
    contact_sheet,
    draw_wrapped,
    load_font,
    relief_panels,
    require_runtime,
    resolve_paths,
    rgb_panel,
    slugify,
    write_tsv_lf,
)
from train_weak_label_rgb_baseline import read_tsv, rel_to_project


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/review_lane_tasks.tsv"
DEFAULT_OUT_TSV = PROJECT_ROOT / "data/weak-label-error-review-workspace-v1/p0_visual_dossier.tsv"
DEFAULT_FIG_DIR = PROJECT_ROOT / "reports/figures/weak_label_p0_pretriage_v1"
DEFAULT_REPORT = PROJECT_ROOT / "reports/weak_label_p0_visual_dossier_v1.md"

GENERATED_AT = "2026-08-01T00:00:00Z"
CARD_HEADER_HEIGHT = 152

GROUP_ORDER = {
    "o_val_local_first": 0,
    "positive_rescue": 1,
    "mamoa_strong_model_confuser": 2,
    "mamoa_archaeological_hard_negative": 3,
    "morphology_rescue": 4,
    "low_rank_positive": 5,
    "weak_negative_later": 6,
}

GROUP_LABELS = {
    "o_val_local_first": "O Val local first",
    "positive_rescue": "positive rescue",
    "mamoa_strong_model_confuser": "mamoa strong model confuser",
    "mamoa_archaeological_hard_negative": "mamoa archaeological hard negative",
    "morphology_rescue": "morphology rescue",
    "low_rank_positive": "low-rank positive",
    "weak_negative_later": "weak negative later",
}

DOSSIER_FIELDS = [
    "dossier_order",
    "pretriage_order",
    "sample_review_key",
    "sample_id",
    "duplicate_rows_in_dossier",
    "source_review_ids",
    "source_queues",
    "source_lanes",
    "source_queue_orders",
    "pretriage_group",
    "pretriage_group_label",
    "pretriage_decision",
    "pretriage_confidence",
    "training_use_after_review",
    "do_not_use_as",
    "review_status",
    "review_notes",
    "final_taxonomy",
    "final_decision",
    "dataset",
    "final_split",
    "label_class",
    "label_role",
    "suggested_taxonomy",
    "name",
    "municipality",
    "parish",
    "country",
    "longitude",
    "latitude",
    "fusion_probability",
    "fusion_rank",
    "max_safety_rank",
    "archetype_only_rank",
    "specialist_probability",
    "specialist_rank",
    "specialist_mean_rank",
    "rank_delta_fusion_to_max",
    "negative_type",
    "morphology_proxy",
    "rgb_status",
    "relief_status",
    "visual_card",
    "group_sheet",
    "full_sheet",
    "visual_reading",
]


def as_int(value: object, fallback: int = 999999) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


def uniq(values: list[str]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        value = value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def group_sort_key(row: dict[str, str]) -> tuple[int, int, int]:
    return (
        GROUP_ORDER.get(row.get("pretriage_group", ""), 99),
        as_int(row.get("pretriage_order")),
        as_int(row.get("specialist_rank")),
    )


def collapse_p0_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    p0_rows = [row for row in rows if row.get("pretriage_order")]
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in p0_rows:
        key = row.get("sample_review_key") or row.get("sample_id")
        grouped[key].append(row)

    collapsed = []
    for sample_key, group_rows in grouped.items():
        group_rows.sort(key=lambda row: (as_int(row.get("pretriage_order")), row.get("queue", ""), row.get("review_id", "")))
        row = dict(group_rows[0])
        row["sample_review_key"] = sample_key
        row["duplicate_rows_in_dossier"] = str(len(group_rows))
        row["source_review_ids"] = ";".join(uniq([source.get("review_id", "") for source in group_rows]))
        row["source_queues"] = ";".join(uniq([source.get("queue", "") for source in group_rows]))
        row["source_lanes"] = ";".join(uniq([source.get("review_lane", "") for source in group_rows]))
        row["source_queue_orders"] = ";".join(
            uniq([f"{source.get('queue', '')}#{source.get('priority_order', '')}" for source in group_rows])
        )
        collapsed.append(row)

    collapsed.sort(key=group_sort_key)
    for idx, row in enumerate(collapsed, start=1):
        row["dossier_order"] = f"{idx:02d}"
        row["pretriage_group_label"] = GROUP_LABELS.get(row.get("pretriage_group", ""), row.get("pretriage_group", ""))
    return collapsed


def chip_status(chip_by_sample: dict[str, dict[str, str]], sample_id: str) -> str:
    return chip_by_sample.get(sample_id, {}).get("image_status", "missing")


def relief_status(relief_by_sample: dict[str, dict[str, str]], sample_id: str) -> str:
    return relief_by_sample.get(sample_id, {}).get("dem_status", "missing")


def ellipsize(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def dossier_card(row: dict[str, str], chip_by_sample: dict[str, dict[str, str]], relief_by_sample: dict[str, dict[str, str]]):
    from PIL import Image, ImageDraw

    title_font = load_font(16, bold=True)
    body_font = load_font(12)
    small_font = load_font(11)

    panels = [rgb_panel(chip_by_sample.get(row["sample_id"])), *relief_panels(relief_by_sample.get(row["sample_id"]))]
    width = len(panels) * PANEL_SIZE
    height = CARD_HEADER_HEIGHT + PANEL_SIZE + TITLE_HEIGHT
    canvas = Image.new("RGB", (width, height), (250, 249, 246))
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([0, 0, width, 30], fill=(24, 26, 28))
    title = f"P0 #{row['dossier_order']} / pretriage {row['pretriage_order']} | {row['name']}"
    place = ", ".join(uniq([row.get("municipality", ""), row.get("parish", ""), row.get("country", "")]))
    draw.text((10, 8), ellipsize(title, 88), fill=(248, 248, 244), font=title_font)
    draw.text((10, 36), ellipsize(place, 100), fill=(48, 50, 52), font=body_font)

    line_1 = (
        f"group={row.get('pretriage_group', '-')} | decision={row.get('pretriage_decision', '-')} | "
        f"confidence={row.get('pretriage_confidence', '-')}"
    )
    line_2 = (
        f"class={row.get('label_class', '-')} taxonomy={row.get('suggested_taxonomy', '-')} | "
        f"fusion_rank={row.get('fusion_rank', '-')} max_rank={row.get('max_safety_rank', '-')} "
        f"spec_rank={row.get('specialist_rank', '-')} mean_rank={row.get('specialist_mean_rank', '-')}"
    )
    line_3 = (
        f"p={row.get('fusion_probability', '-')} spec_p={row.get('specialist_probability', '-')} | "
        f"neg={row.get('negative_type') or '-'} morph={row.get('morphology_proxy') or '-'}"
    )
    line_4 = (
        f"sources={row.get('source_queues', '-')} | rows={row.get('duplicate_rows_in_dossier', '1')} | "
        f"use={row.get('training_use_after_review', '-')}"
    )
    draw.text((10, 56), ellipsize(line_1, 116), fill=(70, 61, 36), font=body_font)
    draw.text((10, 74), ellipsize(line_2, 116), fill=(55, 58, 60), font=small_font)
    draw.text((10, 91), ellipsize(line_3, 116), fill=(55, 58, 60), font=small_font)
    draw.text((10, 108), ellipsize(line_4, 116), fill=(55, 58, 60), font=small_font)
    draw_wrapped(
        draw,
        (10, 125),
        ellipsize(row.get("visual_reading", ""), 150),
        font=small_font,
        fill=(88, 66, 30),
        width_chars=118,
        line_spacing=2,
    )

    for index, image in enumerate(panels):
        canvas.paste(image, (index * PANEL_SIZE, CARD_HEADER_HEIGHT))
    return canvas


def clear_old_figures(fig_dir: Path) -> None:
    if not fig_dir.exists():
        return
    for pattern in ("p0-*.png", "p0-pretriage-*.png"):
        for path in fig_dir.glob(pattern):
            path.unlink()


def write_report(
    path: Path,
    rows: list[dict[str, str]],
    full_sheet: Path,
    group_sheets: dict[str, Path],
    input_rows: int,
) -> None:
    group_counts = Counter(row.get("pretriage_group", "") for row in rows)
    lane_counts = Counter(row.get("source_lanes", "") for row in rows)
    taxonomy_counts = Counter(row.get("suggested_taxonomy", "") for row in rows)
    o_val = [row for row in rows if row.get("pretriage_group") == "o_val_local_first"]

    lines = [
        "# Weak-label P0 pretriage visual dossier v1",
        "",
        f"Generated: {GENERATED_AT}",
        "",
        "## What This Is",
        "",
        "This dossier turns the autonomous P0 pretriage queue into inspectable visual cards.",
        "Each card combines RGB, DEM, slope and local relief with the same 120 m reference radius used by the broader error-review figures.",
        "It is a review aid, not an archaeological acceptance/rejection decision and not a discovery report.",
        "",
        "## Outputs",
        "",
        f"- P0 input rows: `{input_rows}`",
        f"- Unique P0 points after duplicate collapse: `{len(rows)}`",
        f"- Dossier TSV: `data/weak-label-error-review-workspace-v1/p0_visual_dossier.tsv`",
        f"- Full sheet: `{rel_to_project(full_sheet)}`",
        f"- Individual cards: `reports/figures/weak_label_p0_pretriage_v1/p0-*.png`",
        "",
        "## Counts",
        "",
        "### Groups",
        "",
    ]
    for group, count in sorted(group_counts.items(), key=lambda item: GROUP_ORDER.get(item[0], 99)):
        lines.append(f"- `{group}`: `{count}`")
    lines.extend(["", "### Source lanes", ""])
    for lane, count in lane_counts.most_common():
        lines.append(f"- `{lane}`: `{count}`")
    lines.extend(["", "### Suggested taxonomy", ""])
    for taxonomy, count in taxonomy_counts.most_common():
        lines.append(f"- `{taxonomy}`: `{count}`")

    lines.extend(["", "## Group Sheets", ""])
    for group, sheet in sorted(group_sheets.items(), key=lambda item: GROUP_ORDER.get(item[0], 99)):
        lines.append(f"### {GROUP_LABELS.get(group, group)}")
        lines.append("")
        lines.append(f"- rows: `{group_counts[group]}`")
        lines.append(f"- image: `{rel_to_project(sheet)}`")
        lines.append("")
        lines.append(f"![{group}]({rel_to_project(sheet)})")
        lines.append("")

    lines.extend(
        [
            "## O Val Local First",
            "",
            "| Order | Class | Name | Decision | Fusion rank | Max rank | Specialist rank | Card |",
            "|---:|---:|---|---|---:|---:|---:|---|",
        ]
    )
    for row in o_val:
        lines.append(
            f"| {row['dossier_order']} | {row['label_class']} | `{row['name']}` | `{row['pretriage_decision']}` | "
            f"{row['fusion_rank']} | {row['max_safety_rank']} | {row['specialist_rank']} | `{row['visual_card']}` |"
        )

    lines.extend(
        [
            "",
            "## Full P0 Order",
            "",
            "| Order | Group | Class | Taxonomy | Name | Municipality | Decision | Source queues | Card |",
            "|---:|---|---:|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['dossier_order']} | `{row['pretriage_group']}` | {row['label_class']} | `{row['suggested_taxonomy']}` | "
            f"`{row['name']}` | `{row['municipality']}` | `{row['pretriage_decision']}` | `{row['source_queues']}` | `{row['visual_card']}` |"
        )

    lines.extend(
        [
            "",
            "## Next Review Move",
            "",
            "1. Open the `p0_pretriage` layer in the QGIS workspace.",
            "2. Use the dossier order as the review order.",
            "3. For positive castros, draw or refine the visible boundary only when RGB/relief/source context supports it.",
            "4. For mamoas, confirm them as specific archaeological hard negatives and do not reuse them as generic absence.",
            "5. Leave ambiguous points as `non_decidible` or `needs_followup` rather than forcing labels.",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--chip-manifest", type=Path, action="append", default=None)
    parser.add_argument("--relief-manifest", type=Path, action="append", default=None)
    parser.add_argument("--out-tsv", type=Path, default=DEFAULT_OUT_TSV)
    parser.add_argument("--fig-dir", type=Path, default=DEFAULT_FIG_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    args.tasks = args.tasks if args.tasks.is_absolute() else PROJECT_ROOT / args.tasks
    args.chip_manifest = resolve_paths(args.chip_manifest or DEFAULT_CHIP_MANIFESTS)
    args.relief_manifest = resolve_paths(args.relief_manifest or DEFAULT_RELIEF_MANIFESTS)
    args.out_tsv = args.out_tsv if args.out_tsv.is_absolute() else PROJECT_ROOT / args.out_tsv
    args.fig_dir = args.fig_dir if args.fig_dir.is_absolute() else PROJECT_ROOT / args.fig_dir
    args.report = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    return args


def main() -> None:
    require_runtime()
    args = resolve_args(parse_args())
    input_rows = [row for row in read_tsv(args.tasks) if row.get("pretriage_order")]
    rows = collapse_p0_rows(read_tsv(args.tasks))
    chip_by_sample = by_sample(args.chip_manifest)
    relief_by_sample = by_sample(args.relief_manifest)

    args.fig_dir.mkdir(parents=True, exist_ok=True)
    clear_old_figures(args.fig_dir)

    cards_by_group: dict[str, list[object]] = defaultdict(list)
    all_cards = []
    for row in rows:
        row["rgb_status"] = chip_status(chip_by_sample, row["sample_id"])
        row["relief_status"] = relief_status(relief_by_sample, row["sample_id"])
        card = dossier_card(row, chip_by_sample, relief_by_sample)
        card_path = args.fig_dir / f"p0-{row['dossier_order']}-{slugify(row['name'])}.png"
        card.save(card_path, optimize=True)
        row["visual_card"] = rel_to_project(card_path)
        cards_by_group[row["pretriage_group"]].append(card)
        all_cards.append(card)

    group_sheets = {}
    for group, cards in sorted(cards_by_group.items(), key=lambda item: GROUP_ORDER.get(item[0], 99)):
        sheet_path = args.fig_dir / f"p0-pretriage-{slugify(group)}.png"
        contact_sheet(sheet_path, cards)
        group_sheets[group] = sheet_path

    full_sheet = args.fig_dir / "p0-pretriage-all.png"
    contact_sheet(full_sheet, all_cards)

    for row in rows:
        row["group_sheet"] = rel_to_project(group_sheets[row["pretriage_group"]])
        row["full_sheet"] = rel_to_project(full_sheet)

    write_tsv_lf(args.out_tsv, rows, DOSSIER_FIELDS)
    write_report(args.report, rows, full_sheet, group_sheets, len(input_rows))

    print(f"p0_input_rows={len(input_rows)}")
    print(f"unique_p0_points={len(rows)}")
    print(f"cards={len(all_cards)}")
    print(f"group_sheets={len(group_sheets)}")
    print(f"wrote={rel_to_project(args.out_tsv)}")
    print(f"report={rel_to_project(args.report)}")


if __name__ == "__main__":
    main()
