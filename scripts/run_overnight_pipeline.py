#!/usr/bin/env python3
"""Chain the overnight work on the Raspberry and report what happened.

Runs unattended: waits for the dense-grid downloads, scores them, samples and
fetches landscape negatives, then writes one digest. Every step is logged and
resumable, and a failure in one stage does not abort the others.

Deliberately contains no LLM call. Every conclusion below is computed from
the numbers by explicit rules, so it is reproducible and cannot hallucinate.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = Path("/srv/data/castros-ia-logs")
STATE_PATH = LOG_DIR / "overnight_state.json"
DIGEST_PATH = PROJECT_ROOT / "reports/overnight_digest.md"

DENSE_MANIFEST = PROJECT_ROOT / "data/trasancos-dense-v1/trasancos_dense_grid_manifest.tsv"
DENSE_RGB_DIR = PROJECT_ROOT / "data/external/trasancos-dense-v1"
DENSE_DEM_DIR = PROJECT_ROOT / "data/external/weak-label-relief-v1/trasancos_dense_grid"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message: str) -> None:
    print(f"[{now()}] {message}", flush=True)


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1), encoding="utf-8")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, dialect="excel-tab"))


def count_files(directory: Path, suffix: str) -> int:
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.rglob(f"*{suffix}"))


def run(step: str, cmd: list[str], state: dict, timeout: int = 36000) -> bool:
    """Run one stage, recording outcome. Never raises."""
    log(f"START {step}")
    started = time.time()
    try:
        result = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=timeout
        )
        ok = result.returncode == 0
        tail = (result.stdout or "").strip().splitlines()[-12:]
        err = (result.stderr or "").strip().splitlines()[-6:]
        state.setdefault("steps", {})[step] = {
            "ok": ok,
            "returncode": result.returncode,
            "seconds": round(time.time() - started, 1),
            "stdout_tail": tail,
            "stderr_tail": err if not ok else [],
            "finished_at": now(),
        }
        log(f"{'OK' if ok else 'FAIL'} {step} ({round(time.time()-started)}s)")
        for line in tail[-4:]:
            log(f"    {line}")
    except subprocess.TimeoutExpired:
        state.setdefault("steps", {})[step] = {
            "ok": False,
            "returncode": "timeout",
            "seconds": round(time.time() - started, 1),
            "stdout_tail": [],
            "stderr_tail": ["timed out"],
            "finished_at": now(),
        }
        log(f"TIMEOUT {step}")
        ok = False
    except Exception as exc:  # keep the chain alive
        state.setdefault("steps", {})[step] = {
            "ok": False,
            "returncode": "exception",
            "seconds": round(time.time() - started, 1),
            "stdout_tail": [],
            "stderr_tail": [str(exc)[:400]],
            "finished_at": now(),
        }
        log(f"ERROR {step}: {exc}")
        ok = False
    save_state(state)
    return ok


def wait_for_downloads(state: dict, args: argparse.Namespace) -> dict:
    """Block until RGB and DEM stop growing, or the deadline passes."""
    total = sum(1 for _ in DENSE_MANIFEST.open(encoding="utf-8")) - 1 if DENSE_MANIFEST.exists() else 0
    log(f"waiting for dense-grid downloads (target {total})")
    deadline = time.time() + args.download_wait_hours * 3600
    last = (-1, -1)
    stalled_since = None

    while time.time() < deadline:
        png = count_files(DENSE_RGB_DIR, ".png")
        tif = count_files(DENSE_DEM_DIR, ".tif")
        running = subprocess.run(
            ["pgrep", "-f", "export_weak_label_(chips|relief)"], capture_output=True, text=True
        ).returncode == 0

        if png >= total * args.min_fraction and tif >= total * args.min_fraction:
            log(f"downloads complete enough: png={png} tif={tif} of {total}")
            break
        if not running:
            log(f"exporters no longer running: png={png} tif={tif} of {total}")
            break
        if (png, tif) == last:
            stalled_since = stalled_since or time.time()
            if time.time() - stalled_since > args.stall_minutes * 60:
                log(f"downloads stalled {args.stall_minutes} min: png={png} tif={tif}")
                break
        else:
            stalled_since = None
            last = (png, tif)
            log(f"progress png={png} tif={tif} of {total}")
        time.sleep(args.poll_seconds)

    png, tif = count_files(DENSE_RGB_DIR, ".png"), count_files(DENSE_DEM_DIR, ".tif")
    state["downloads"] = {"target": total, "png": png, "tif": tif, "checked_at": now()}
    save_state(state)
    return state["downloads"]


def analyse_dense_ranking(path: Path) -> dict:
    """Recall of catalogued castros on the dense grid, against its own ceiling."""
    if not path.exists():
        return {}
    rows = [r for r in read_tsv(path) if r.get("status") == "ok" and r.get("sea_or_flat") == "no"]
    if not rows:
        return {}
    rows.sort(key=lambda r: float(r["probability"]), reverse=True)
    n = len(rows)
    cut = max(1, n // 10)

    best: dict[str, tuple[int, dict]] = {}
    for index, row in enumerate(rows, start=1):
        name = row.get("known_site_name", "")
        if not name:
            continue
        if name not in best or index < best[name][0]:
            best[name] = (index, row)

    castros = {k: v for k, v in best.items() if v[1].get("candidate_class") == "known_castro_recovered"}
    in_top = [k for k, v in castros.items() if v[0] <= cut]
    misses = sorted(
        [(v[0], k) for k, v in castros.items() if v[0] > cut], key=lambda item: item[0], reverse=True
    )
    return {
        "land_cells": n,
        "distinct_castros": len(castros),
        "in_top_decile": len(in_top),
        "recall": round(len(in_top) / len(castros), 4) if castros else None,
        "worst_misses": [{"rank": r, "name": k} for r, k in misses[:10]],
    }


def write_digest(state: dict, args: argparse.Namespace) -> None:
    steps = state.get("steps", {})
    downloads = state.get("downloads", {})
    dense = state.get("dense_analysis", {})

    ok_steps = [k for k, v in steps.items() if v.get("ok")]
    bad_steps = [k for k, v in steps.items() if not v.get("ok")]

    lines = [
        "# Overnight run digest",
        "",
        f"Written at: `{now()}`",
        f"Started at: `{state.get('started_at', 'unknown')}`",
        "",
        "## Read this first",
        "",
    ]

    # Rule-based verdict. No model involved.
    if bad_steps:
        lines.append(f"- **{len(bad_steps)} stage(s) failed**: `{', '.join(bad_steps)}`. See detail below.")
    else:
        lines.append("- All stages completed without error.")

    if downloads:
        target = downloads.get("target", 0) or 1
        pct_png = downloads.get("png", 0) / target
        pct_tif = downloads.get("tif", 0) / target
        lines.append(
            f"- Dense grid downloads: RGB `{downloads.get('png',0)}/{target}` (`{pct_png:.0%}`), "
            f"DEM `{downloads.get('tif',0)}/{target}` (`{pct_tif:.0%}`)."
        )
        if min(pct_png, pct_tif) < 0.95:
            lines.append("  - **Incomplete.** The scoring below covers only what downloaded.")

    if dense:
        recall = dense.get("recall")
        lines.append(
            f"- Dense-grid sanity check: `{dense.get('in_top_decile')}/{dense.get('distinct_castros')}` "
            f"catalogued castros in the top decile of `{dense.get('land_cells')}` land cells "
            f"(recall `{recall:.0%}`)." if recall is not None else "- Dense-grid sanity check unavailable."
        )
        if recall is not None:
            # The 512 m grid scored 18%; the O Val 128 m contraprueba scored 71%.
            if recall >= 0.55:
                lines.append("  - **Confirms the overlap fix at comarca scale.** Proceed to candidate review.")
            elif recall >= 0.30:
                lines.append("  - **Partial improvement** over the 18% of the 512 m grid, below the 71% seen on O Val. Worth understanding why before trusting the candidate list.")
            else:
                lines.append("  - **Does not reproduce the O Val result.** Do not use the candidate list; the overlap fix did not transfer to the full comarca.")

    lines += ["", "## Stages", "", "| stage | result | seconds |", "|---|---|---:|"]
    for name, info in steps.items():
        lines.append(f"| `{name}` | {'ok' if info.get('ok') else 'FAILED'} | `{info.get('seconds','')}` |")

    if dense.get("worst_misses"):
        lines += [
            "",
            "## Catalogued castros the dense grid still misses",
            "",
            "| rank | site |",
            "|---:|---|",
        ]
        for miss in dense["worst_misses"]:
            lines.append(f"| `{miss['rank']}` | {miss['name']} |")

    lines += ["", "## Stage output", ""]
    for name, info in steps.items():
        lines.append(f"### `{name}`")
        lines.append("")
        for line in info.get("stdout_tail", []) or ["(no output)"]:
            lines.append(f"    {line}")
        if info.get("stderr_tail"):
            lines.append("")
            lines.append("errors:")
            for line in info["stderr_tail"]:
                lines.append(f"    {line}")
        lines.append("")

    lines += [
        "## Standing cautions",
        "",
        "- Weak labels throughout; a high score is a shape prior, not a site.",
        "- Landscape negatives are positive-unlabeled: sampled ground is not verified empty.",
        "- No precise coordinate of an uncatalogued cell leaves this machine.",
        "",
    ]
    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"digest written to {DIGEST_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--download-wait-hours", type=float, default=14.0)
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--stall-minutes", type=int, default=25)
    parser.add_argument("--min-fraction", type=float, default=0.98)
    parser.add_argument("--negative-samples", type=int, default=6000)
    parser.add_argument("--skip-wait", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = load_state()
    state["started_at"] = state.get("started_at") or now()
    save_state(state)
    python = sys.executable

    # 1. Landscape negatives: sample now, fetch while the dense grid downloads.
    run(
        "landscape_negative_sample",
        [python, "scripts/build_landscape_negative_bank.py", "--samples", str(args.negative_samples)],
        state,
        timeout=1800,
    )
    neg_manifest = PROJECT_ROOT / "data/landscape-negatives-v1/landscape_negative_manifest.tsv"
    if neg_manifest.exists():
        run(
            "landscape_negative_rgb",
            [
                python, "scripts/export_weak_label_chips.py",
                "--input", str(neg_manifest),
                "--out-manifest", "data/landscape-negatives-v1/landscape_negative_rgb_manifest.tsv",
                "--report", "reports/landscape_negative_rgb_export.md",
                "--workers", "4", "--ign-parallel", "3",
            ],
            state,
            timeout=28800,
        )
        run(
            "landscape_negative_dem",
            [
                python, "scripts/export_weak_label_relief_wcs.py",
                "--input", str(neg_manifest),
                "--out-manifest", "data/landscape-negatives-v1/landscape_negative_dem_manifest.tsv",
                "--report", "reports/landscape_negative_dem_export.md",
                "--workers", "4", "--wcs-parallel", "3",
            ],
            state,
            timeout=28800,
        )

    # 2. Wait for the dense grid, then score it in parallel.
    if not args.skip_wait:
        wait_for_downloads(state, args)

    if DENSE_MANIFEST.exists():
        run(
            "dense_grid_score",
            [
                python, "scripts/build_trasancos_inference_ranking.py",
                "--stage", "score",
                "--grid-manifest", str(DENSE_MANIFEST),
                "--grid-split", "trasancos_dense_grid",
                "--chip-root", "data/external/trasancos-dense-v1",
                "--out-dir", "data/trasancos-dense-v1",
                "--report", "reports/trasancos_dense_ranking_v1.md",
                "--score-workers", str(args.workers),
                "--progress-every", "1000",
            ],
            state,
            timeout=36000,
        )
        state["dense_analysis"] = analyse_dense_ranking(
            PROJECT_ROOT / "data/trasancos-dense-v1/trasancos_inference_ranking.tsv"
        )
        save_state(state)

    write_digest(state, args)
    log("overnight pipeline finished")


if __name__ == "__main__":
    main()
